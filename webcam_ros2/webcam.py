import glob
import subprocess
import threading

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from turbojpeg import TurboJPEG, TJPF_BGR


class WebcamNode(Node):
    def __init__(self):
        super().__init__('webcam_node')

        self.declare_parameter('camera_id',            0)
        self.declare_parameter('camera_name',          'camera')
        self.declare_parameter('width',                640)
        self.declare_parameter('height',               480)
        self.declare_parameter('fps',                  30)
        self.declare_parameter('serial_number',        '')
        self.declare_parameter('power_line_frequency', -1)

        cam_id              = self.get_parameter('camera_id').value
        cam_name            = self.get_parameter('camera_name').value
        width               = self.get_parameter('width').value
        height              = self.get_parameter('height').value
        fps                 = self.get_parameter('fps').value
        serial_number       = self.get_parameter('serial_number').value
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

        self.jpeg = TurboJPEG()
        self.cam_name = cam_name
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        topic = f'{cam_name}/color/image_raw/compressed'
        self.publisher = self.create_publisher(CompressedImage, topic, 10)
        self.timer = self.create_timer(1.0 / fps, self.publish_image)

        self.get_logger().info(
            f'[{cam_name}] 시작 | id={cam_id} | {width}x{height} @ {fps}fps | topic={topic}'
        )

    def find_camera_by_serial(self, serial_number: str) -> int:
        for dev_path in sorted(glob.glob('/dev/video*')):
            try:
                result = subprocess.run(
                    ['udevadm', 'info', dev_path],
                    capture_output=True, text=True, timeout=2
                )
                for line in result.stdout.splitlines():
                    if line.strip().startswith('E: ID_SERIAL_SHORT='):
                        found_serial = line.strip().split('=', 1)[1]
                        if found_serial == serial_number:
                            dev_index = int(dev_path.replace('/dev/video', ''))
                            return dev_index
            except (subprocess.TimeoutExpired, ValueError):
                continue
        return -1

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
        msg.data = self.jpeg.encode(frame, pixel_format=TJPF_BGR)

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
