import ctypes
import fcntl
import glob
import os
import re
import subprocess
import threading

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
try:
    # from turbojpeg import TurboJPEG, TJPF_BGR
    ENCODE = 'turbojpeg'
except Exception as e:
    ENCODE = 'cv'   
ENCODE = 'cv'   

class WebcamNode(Node):
    def __init__(self):
        super().__init__('webcam_node')

        self.declare_parameter('camera_id',            0)
        self.declare_parameter('camera_name',          'camera')
        self.declare_parameter('width',                640)
        self.declare_parameter('height',               480)
        self.declare_parameter('fps',                  30)
        self.declare_parameter('serial_number',        '')
        self.declare_parameter('topic',                '')
        self.declare_parameter('power_line_frequency', -1)

        cam_id              = self.get_parameter('camera_id').value
        cam_name            = self.get_parameter('camera_name').value
        width               = self.get_parameter('width').value
        height              = self.get_parameter('height').value
        fps                 = self.get_parameter('fps').value
        serial_number       = self.get_parameter('serial_number').value
        topic               = self.get_parameter('topic').value
        power_line_freq     = self.get_parameter('power_line_frequency').value

        if serial_number:
            cam_id = self.find_camera_by_serial(serial_number)
            if cam_id == -1:
                self.get_logger().error(
                    f'[{cam_name}] serial_number={serial_number} 에 해당하는 카메라를 찾을 수 없습니다.'
                )
                raise RuntimeError(f'Cannot find camera with serial={serial_number}')
            self.get_logger().info(f'[{cam_name}] serial={serial_number} → /dev/video{cam_id} 매칭')

        dev_path = f'/dev/video{cam_id}'
        if power_line_freq >= 0:
            try:
                subprocess.run(
                    ['v4l2-ctl', '-d', dev_path,
                     f'--set-ctrl=power_line_frequency={power_line_freq}'],
                    check=True, timeout=3
                )
                self.get_logger().info(
                    f'[{cam_name}] power_line_frequency={power_line_freq} 설정 완료'
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.get_logger().warn(f'[{cam_name}] v4l2-ctl 실행 실패: {e}')

        self.cap = cv2.VideoCapture(cam_id, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FOURCC,       cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS,          fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

        if not self.cap.isOpened():
            self.get_logger().error(f'[{cam_name}] 카메라(id={cam_id})를 열 수 없습니다.')
            raise RuntimeError(f'Cannot open camera id={cam_id}')

        if ENCODE == 'turbojpeg':
            self.jpeg = TurboJPEG()
        self.cam_name = cam_name
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        self.publisher = self.create_publisher(CompressedImage, topic, 10)
        self.timer = self.create_timer(1.0 / fps, self.publish_image)

        self.get_logger().info(
            f'[{cam_name}] 시작 | id={cam_id} | {width}x{height} @ {fps}fps | topic={topic}'
        )

    def find_camera_by_serial(self, serial_number: str) -> int:
        """serial_number 가 일치하면서 실제 영상 캡처가 가능한 /dev/videoN 을 찾는다.

        USB 카메라 하나가 여러 개의 /dev/videoN 을 만드는 경우가 많다
        (예: Arducam UC684 -> video6~video9). 이 중 VIDEO_CAPTURE 능력이 있는
        노드만 실제로 열 수 있으므로, serial 이 맞더라도 capture 노드인지
        반드시 확인해야 한다.
        """
        candidates = []
        for dev_path in glob.glob('/dev/video*'):
            m = re.fullmatch(r'/dev/video(\d+)', dev_path)
            if not m:
                continue
            dev_index = int(m.group(1))

            sysfs = f'/sys/class/video4linux/video{dev_index}'
            found_serial = self._read_sysfs_serial(sysfs)
            if found_serial is None or found_serial != serial_number:
                continue

            # 같은 카메라의 여러 노드 중 index 가 작은 쪽이 보통 capture 노드다.
            try:
                with open(f'{sysfs}/index') as f:
                    order = int(f.read().strip())
            except (OSError, ValueError):
                order = dev_index

            candidates.append((order, dev_index))

        if not candidates:
            return -1

        candidates.sort()
        denied = []
        unknown = []
        for _, dev_index in candidates:
            status = self._is_capture_device(dev_index)
            if status is True:
                return dev_index
            if status == 'permission_denied':
                denied.append(dev_index)
            elif status == 'unknown':
                unknown.append(dev_index)

        if denied and not unknown:
            # 전부 권한 문제라면 추측해서 진행해봐야 OpenCV 쪽에서
            # 원인을 알기 어려운 에러로 다시 실패한다. 여기서 명확히 끊는다.
            nodes = ', '.join(f'/dev/video{i}' for i in denied)
            raise PermissionError(
                f'serial={serial_number} 카메라({nodes})에 접근할 수 없습니다. '
                f'현재 사용자를 video 그룹에 추가한 뒤 다시 로그인하세요: '
                f'sudo usermod -aG video $USER'
            )

        if unknown:
            # QUERYCAP 을 지원하지 않는 환경 -> 기존처럼 첫 후보로 진행
            first = unknown[0]
            self.get_logger().warn(
                f'serial={serial_number}: capture 능력을 확인할 수 없어 '
                f'/dev/video{first} 로 진행합니다.'
            )
            return first

        return -1

    @staticmethod
    def _read_sysfs_serial(sysfs_path: str):
        """video 노드가 속한 USB device 의 serial 을 sysfs 에서 읽는다."""
        try:
            device = os.path.realpath(os.path.join(sysfs_path, 'device'))
        except OSError:
            return None

        # USB device 디렉토리(serial 파일이 있는 곳)까지 상위로 올라간다.
        for _ in range(6):
            serial_file = os.path.join(device, 'serial')
            if os.path.isfile(serial_file):
                try:
                    with open(serial_file) as f:
                        return f.read().strip()
                except OSError:
                    return None
            parent = os.path.dirname(device)
            if parent == device:
                break
            device = parent
        return None

    def _is_capture_device(self, dev_index: int):
        """VIDIOC_QUERYCAP 으로 VIDEO_CAPTURE 능력을 확인한다.

        True / False 외에 'permission_denied'(권한 없음), 'unknown'(QUERYCAP
        미지원)을 반환하여 호출측이 상황을 구분할 수 있게 한다.
        """
        V4L2_CAP_VIDEO_CAPTURE = 0x00000001
        V4L2_CAP_DEVICE_CAPS   = 0x80000000
        VIDIOC_QUERYCAP        = 0x80685600

        class _Capability(ctypes.Structure):
            _fields_ = [
                ('driver',       ctypes.c_char * 16),
                ('card',         ctypes.c_char * 32),
                ('bus_info',     ctypes.c_char * 32),
                ('version',      ctypes.c_uint32),
                ('capabilities', ctypes.c_uint32),
                ('device_caps',  ctypes.c_uint32),
                ('reserved',     ctypes.c_uint32 * 3),
            ]

        cap = _Capability()
        try:
            fd = os.open(f'/dev/video{dev_index}', os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            # 노드는 존재하지만 권한이 없다. 능력을 알 수 없는 것과는 다르므로
            # 호출측이 명확한 안내를 할 수 있게 구분해서 알린다.
            return 'permission_denied'
        except OSError as e:
            self.get_logger().warn(f'/dev/video{dev_index} 열기 실패: {e}')
            return False
        try:
            fcntl.ioctl(fd, VIDIOC_QUERYCAP, cap)
        except OSError:
            return 'unknown'
        finally:
            os.close(fd)

        caps = cap.device_caps if cap.capabilities & V4L2_CAP_DEVICE_CAPS else cap.capabilities
        return bool(caps & V4L2_CAP_VIDEO_CAPTURE)

    def _capture_loop(self):
        while rclpy.ok() and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                with self.frame_lock:
                    self.latest_frame = frame

    def publish_image(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return
            frame = self.latest_frame

        # frame = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)

        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.format = 'jpeg'
        if ENCODE == 'turbojpeg':
            d = self.jpeg.encode(frame, pixel_format=TJPF_BGR)
        elif ENCODE == 'cv':
            d = np.array(cv2.imencode('.jpg', frame)[1]).tobytes()
        msg.data = d

        self.publisher.publish(msg)

    def destroy_node(self):
        self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = WebcamNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down.')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
