# webcam_ros2

USB 웹캠을 ROS2 토픽으로 퍼블리시하는 패키지입니다.  
다중 카메라를 지원하며, `config/camera_config.yaml`을 통해 카메라를 설정합니다.  
출력 토픽은 JPEG 압축된 `sensor_msgs/CompressedImage`입니다.

---

## 패키지 구조

```
webcam_ros2/
├── config/
│   └── camera_config.yaml       # 카메라 설정 파일
├── launch/
│   └── webcam.launch.py         # 런치 파일
├── webcam_ros2/
│   └── webcam.py                # 웹캠 노드
├── package.xml
├── setup.py
└── README.md
```

---

## 의존성

```bash
sudo apt install ros-$ROS_DISTRO-cv-bridge python3-opencv
```

---

## 빌드

```bash
cd ~/ros_ws/webcam_ws
colcon build --packages-select webcam_ros2
source install/setup.bash
```

---

## 실행

```bash
ros2 launch webcam_ros2 webcam.launch.py
```

---

## 카메라 설정 (`config/camera_config.yaml`)

카메라 추가/수정은 이 파일만 편집하면 됩니다.

```yaml
webcam_node:
  ros__parameters:
    cameras:
      - id: 0                      # 카메라 장치 인덱스 (serial_number 미설정 시 사용)
        name: "front"              # 카메라 이름 → 토픽 이름에 반영됨
        width: 1280                # 해상도 (가로)
        height: 720                # 해상도 (세로)
        fps: 30                    # 프레임 레이트
        serial_number: "187C02F5"  # USB 시리얼 번호 (설정 시 자동 탐색)
```

### 파라미터 설명

| 파라미터 | 타입 | 설명 |
|---|---|---|
| `id` | int | `/dev/videoN` 인덱스. `serial_number` 설정 시 무시됨 |
| `name` | string | 카메라 식별 이름. 출력 토픽 경로에 사용됨 |
| `width` | int | 캡처 해상도 가로 (픽셀) |
| `height` | int | 캡처 해상도 세로 (픽셀) |
| `fps` | int | 캡처 및 퍼블리시 프레임 레이트 |
| `serial_number` | string | USB 시리얼 번호. 설정 시 `udevadm`으로 장치를 자동 탐색 |

### 다중 카메라 추가

`cameras` 리스트에 항목을 추가하면 카메라 수만큼 노드가 자동으로 실행됩니다.

```yaml
cameras:
  - id: 0
    name: "front"
    width: 1280
    height: 720
    fps: 30
    serial_number: "187C02F5"
  - id: 1
    name: "side"
    width: 640
    height: 480
    fps: 30
    serial_number: "2A3F10B1"
```

---

## 출력 토픽

카메라 `name`을 기반으로 토픽이 자동 생성됩니다.

| 카메라 name | 토픽 |
|---|---|
| `front` | `/front/webcam/image/compressed` |
| `side` | `/side/webcam/image/compressed` |

토픽 확인:
```bash
ros2 topic list
ros2 topic hz /front/webcam/image/compressed
```

---

## serial_number 확인 방법

카메라를 USB에 연결한 후 아래 명령어로 시리얼 번호를 확인합니다.

```bash
udevadm info /dev/video0 | grep ID_SERIAL_SHORT
# 출력 예시: E: ID_SERIAL_SHORT=187C02F5
```

`/dev/video*` 장치가 여러 개인 경우 번호를 바꿔가며 확인합니다.
