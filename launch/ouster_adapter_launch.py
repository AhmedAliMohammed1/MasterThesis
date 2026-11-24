"""Standalone live Ouster adapter; start the detector separately on output_topic."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    defaults = {
        'input_topic': '/ouster1/points',
        'output_topic': '/point_cloud',
        'intensity_source': 'reflectivity',
        'intensity_divisor': '255.0',
        'intensity_clip_max': '0.0',
    }
    arguments = [DeclareLaunchArgument(name, default_value=value)
                 for name, value in defaults.items()]
    parameters = {name: ParameterValue(LaunchConfiguration(name), value_type=str)
                  for name in defaults if name not in ('intensity_divisor', 'intensity_clip_max')}
    parameters['intensity_divisor'] = ParameterValue(
        LaunchConfiguration('intensity_divisor'), value_type=float)
    parameters['intensity_clip_max'] = ParameterValue(
        LaunchConfiguration('intensity_clip_max'), value_type=float)
    return LaunchDescription(arguments + [Node(
        package='pp_infer', executable='ouster_adapter', output='screen',
        parameters=[parameters])])
