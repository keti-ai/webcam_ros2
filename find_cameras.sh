#!/bin/bash
# 연결된 카메라 중 실제 영상 캡처가 가능한 노드만 찾아 USB 포트 경로와 함께 출력한다.
# 출력된 by-path 경로를 config/camera_config.yaml 의 device_path 에 넣으면
# 같은 USB 포트에 꽂혀 있는 한 /dev/videoN 번호가 바뀌어도 같은 카메라를 연다.
#
# 사용법: ./find_cameras.sh [-v]   (-v: 지원 포맷/해상도까지 출력)

VERBOSE=0
[ "$1" = "-v" ] && VERBOSE=1

if ! command -v v4l2-ctl >/dev/null 2>&1; then
    echo "v4l2-ctl 이 없습니다: sudo apt install v4l-utils" >&2
    exit 1
fi

found=0
for dev in /dev/video*; do
    [ -e "$dev" ] || continue

    # 메타데이터 노드 등 캡처가 불가능한 노드는 제외
    if ! v4l2-ctl -d "$dev" --info 2>/dev/null \
        | sed -n '/Device Caps/,$p' | grep -q "Video Capture"; then
        continue
    fi

    props=$(udevadm info "$dev" 2>/dev/null)
    get() { echo "$props" | sed -n "s/^E: $1=//p"; }

    product=$(get ID_V4L_PRODUCT)
    vid=$(get ID_VENDOR_ID)
    pid=$(get ID_MODEL_ID)
    serial=$(get ID_SERIAL_SHORT)
    id_path=$(get ID_PATH)

    by_path=""
    for link in /dev/v4l/by-path/*; do
        [ "$(readlink -f "$link")" = "$dev" ] || continue
        # usbv2 별칭보다 usb- 경로를 우선 사용
        case "$link" in
            *-usbv2-*) [ -z "$by_path" ] && by_path="$link" ;;
            *) by_path="$link" ;;
        esac
    done

    found=$((found + 1))
    echo "=== $dev ==="
    echo "  product     : $product"
    echo "  usb id      : ${vid}:${pid}"
    echo "  serial      : ${serial:-(없음)}"
    echo "  usb port    : ${id_path:-(알 수 없음)}"
    echo "  device_path : ${by_path:-(없음)}"
    if [ "$VERBOSE" -eq 1 ]; then
        v4l2-ctl -d "$dev" --list-formats-ext 2>/dev/null | sed 's/^/    /'
    fi
    echo ""
done

[ "$found" -eq 0 ] && echo "캡처 가능한 카메라가 없습니다."
echo "총 ${found}개 캡처 장치"
