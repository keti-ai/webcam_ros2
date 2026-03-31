#!/bin/bash
echo "=== Finding HD 4MP WEBCAM devices ==="
for dev in /dev/video*; do
    product=$(udevadm info "$dev" 2>/dev/null | grep "ID_V4L_PRODUCT" | sed 's/.*ID_V4L_PRODUCT=//')
    echo "$dev: '$product'"  # 실제 값 확인용
done

echo ""
for dev in /dev/video*; do
    product=$(udevadm info "$dev" 2>/dev/null | grep "ID_V4L_PRODUCT" | sed 's/.*ID_V4L_PRODUCT=//')
    if [ "$product" = "webcam: HD 4MP WEBCAM" ]; then
        formats=$(v4l2-ctl -d "$dev" --list-formats 2>/dev/null)
        echo "$dev: '$formats'"
    fi
done


echo ""
echo "=== Finding HD 4MP WEBCAM (Video Capture only) ==="
echo ""
for dev in /dev/video*; do
    product=$(udevadm info "$dev" 2>/dev/null | grep "ID_V4L_PRODUCT" | sed 's/.*ID_V4L_PRODUCT=//')
    if [ "$product" = "webcam: HD 4MP WEBCAM" ]; then
        formats=$(v4l2-ctl -d "$dev" --list-formats 2>/dev/null)
        if echo "$formats" | grep -q "MJPG"; then
            echo "$dev"
        fi
    fi
done