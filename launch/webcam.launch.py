import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory('webcam_ros2'),
        'config',
        'camera_config.yaml'
    )

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    cameras = config['webcam_node']['ros__parameters']['cameras']

    nodes = []
    for cam in cameras:
        node = Node(
            package='webcam_ros2',
            executable='webcam_node',
            name=f'webcam_node_{cam["name"]}',
            parameters=[{
                'camera_id':            cam['id'],
                'camera_name':          cam['name'],
                'width':                cam['width'],
                'height':               cam['height'],
                'fps':                  cam['fps'],
                'serial_number':        cam['serial_number'],
                'topic':                cam['topic'],
                'power_line_frequency': cam.get('power_line_frequency', -1),
            }],
            output='screen',
        )
        nodes.append(node)

    return LaunchDescription(nodes)
