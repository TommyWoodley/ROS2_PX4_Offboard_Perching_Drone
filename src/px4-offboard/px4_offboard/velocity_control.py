#!/usr/bin/env python

__author__ = "Braden Wagstaff"
__contact__ = "bradenwagstaff1@gmail.com"

import rclpy
from rclpy.node import Node
import numpy as np
from rclpy.clock import Clock
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy, QoSDurabilityPolicy

from px4_msgs.msg import OffboardControlMode
from px4_msgs.msg import TrajectorySetpoint
from px4_msgs.msg import VehicleStatus
from px4_msgs.msg import VehicleAttitude
from px4_msgs.msg import VehicleCommand
from geometry_msgs.msg import Twist, Vector3
from math import pi
# from tf.transformations import euler_from_quaternion

class OffboardControl(Node):

    def __init__(self):
        super().__init__('minimal_publisher')
        qos_profile = QoSProfile(
            reliability=QoSReliabilityPolicy.RMW_QOS_POLICY_RELIABILITY_BEST_EFFORT,
            durability=QoSDurabilityPolicy.RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.RMW_QOS_POLICY_HISTORY_KEEP_LAST,
            depth=1
        )

        self.status_sub = self.create_subscription(
            VehicleStatus,
            '/fmu/out/vehicle_status',
            self.vehicle_status_callback,
            qos_profile)
        
        self.offboard_velocity_sub = self.create_subscription(
            Twist,
            '/offboard_velocity_cmd',
            self.offboard_velocity_callback,
            qos_profile)
        
        self.attitude_sub = self.create_subscription(
            VehicleAttitude,
            '/fmu/out/vehicle_attitude',
            self.attitude_callback,
            qos_profile)

        self.publisher_offboard_mode = self.create_publisher(OffboardControlMode, '/fmu/in/offboard_control_mode', qos_profile)
        self.publisher_velocity = self.create_publisher(Twist, '/fmu/in/setpoint_velocity/cmd_vel_unstamped', qos_profile)
        self.publisher_trajectory = self.create_publisher(TrajectorySetpoint, '/fmu/in/trajectory_setpoint', qos_profile)
        self.vehicle_command_publisher_ = self.create_publisher(VehicleCommand, "/fmu/in/vehicle_command", 10)

        self.offboard_setpoint_counter_ = 0
        
        arm_timer_period = .1
        self.arm_timer_ = self.create_timer(arm_timer_period, self.arm_timer_callback)

        timer_period = 0.02  # seconds
        # self.timer = self.create_timer(timer_period, self.cmdloop_callback)

        self.nav_state = VehicleStatus.NAVIGATION_STATE_MAX
        self.dt = timer_period
        self.velocity = Vector3()
        self.yaw = 0.0
        self.trueYaw = 0.0
        self.offboardMode = False

    def arm_timer_callback(self):
        self.get_logger().error('SetpointCounter: %s' % self.offboard_setpoint_counter_)
        if(self.offboard_setpoint_counter_ >= 100 and self.offboard_setpoint_counter_ < 120):
            # Change to Offboard mode after 10 setpoints
            self.publish_vehicle_command(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1., 6.)
            # Arm the vehicle
            self.arm()
            self.offboardMode = True


            # stop the counter after reaching 11
        if (self.offboard_setpoint_counter_ < 1020):
            self.offboard_setpoint_counter_ += 1

        if(self.nav_state == VehicleStatus.ARMING_STATE_ARMED):
            self.take_off()

    # Arm the vehicle
    def arm(self):
        self.publish_vehicle_command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0)
        self.get_logger().info("Arm command send")

    def publish_vehicle_command(self, command, param1=0.0, param2=0.0):
        msg = VehicleCommand()
        msg.param1 = param1
        msg.param2 = param2
        msg.command = command  # command ID
        msg.target_system = 1  # system which should execute the command
        msg.target_component = 1  # component which should execute the command, 0 for all components
        msg.source_system = 1  # system sending the command
        msg.source_component = 1  # component sending the command
        msg.from_external = True
        msg.timestamp = int(Clock().now().nanoseconds / 1000) # time in microseconds
        self.vehicle_command_publisher_.publish(msg)

    def vehicle_status_callback(self, msg):
        # TODO: handle NED->ENU transformation
        print("NAV_STATUS: ", msg.nav_state)
        print("  - offboard status: ", VehicleStatus.NAVIGATION_STATE_OFFBOARD)
        self.nav_state = msg.nav_state

    def take_off(self):
        offboard_msg = OffboardControlMode()
        offboard_msg.timestamp = int(Clock().now().nanoseconds / 1000)
        offboard_msg.position = True
        offboard_msg.velocity = False
        offboard_msg.acceleration = False
        self.publisher_offboard_mode.publish(offboard_msg)

        trajectory_msg = TrajectorySetpoint()
        trajectory_msg.position[0] = 0.0
        trajectory_msg.position[1] = 0.0
        trajectory_msg.position[2] = -5.0
        self.publisher_trajectory.publish(trajectory_msg)

    # def flu_to_ned(flu):
    #     #'''Converts Forward-Left-Up (ROS) coordinates to North-East-Down (PX4) coordinates.'''
    #     ned = Vector3()
    #     ned.x = -flu.y  # North = -Left
    #     ned.y = flu.x   # East = Forward
    #     ned.z = -flu.z  # Down = -Up
    #     return ned


    def offboard_velocity_callback(self, msg):
        # Implement your logic here
        # flu_velocity = Vector3()
        # flu_velocity = msg.linear
        # self.velocity = self.flu_to_ned(flu_velocity) #convert to NED

        self.velocity.x = -msg.linear.y
        self.velocity.y = msg.linear.x
        self.velocity.z = -msg.linear.z

        self.yaw = msg.angular.z

        # cos_yaw = np.cos(self.yaw)
        # sin_yaw = np.sin(self.yaw)
        # self.velocity.x = msg.linear.x * cos_yaw - msg.linear.y * sin_yaw
        # self.velocity.y = msg.linear.x * sin_yaw + msg.linear.y * cos_yaw
        # self.velocity.z = msg.linear.z
        # self.yaw = msg.angular.z

    def attitude_callback(self, msg):
        orientation_q = msg.q
        self.trueYaw = -(np.arctan2(2.0*(orientation_q[3]*orientation_q[0] + orientation_q[1]*orientation_q[2]), 
                                  1.0 - 2.0*(orientation_q[0]*orientation_q[0] + orientation_q[1]*orientation_q[1])))
        # self.get_logger().error('TrueYaw: %s' % self.trueYaw)
        

    def cmdloop_callback(self):
        # Publish offboard control modes
        offboard_msg = OffboardControlMode()
        offboard_msg.timestamp = int(Clock().now().nanoseconds / 1000)
        offboard_msg.position = False
        offboard_msg.velocity = True
        offboard_msg.acceleration = False
        self.publisher_offboard_mode.publish(offboard_msg)


        if self.nav_state == VehicleStatus.NAVIGATION_STATE_OFFBOARD or self.offboardMode == True:
            # self.get_logger().error('OFFBOARD ON')
            

            # Compute velocity in the world frame
            cos_yaw = np.cos(self.trueYaw)
            sin_yaw = np.sin(self.trueYaw)
            velocity_world_x = (self.velocity.x * cos_yaw - self.velocity.y * sin_yaw)
            velocity_world_y = (self.velocity.x * sin_yaw + self.velocity.y * cos_yaw)

            # Create and publish Twist message
            # twist_msg = Twist()
            # twist_msg.linear = self.velocity
            # self.publisher_velocity.publish(twist_msg)

            # Create and publish TrajectorySetpoint message with NaN values for position and acceleration
            trajectory_msg = TrajectorySetpoint()
            trajectory_msg.timestamp = int(Clock().now().nanoseconds / 1000)
            trajectory_msg.velocity[0] = velocity_world_x
            trajectory_msg.velocity[1] = velocity_world_y
            trajectory_msg.velocity[2] = self.velocity.z
            trajectory_msg.position[0] = float('nan')
            trajectory_msg.position[1] = float('nan')
            trajectory_msg.position[2] = float('nan')
            trajectory_msg.acceleration[0] = float('nan')
            trajectory_msg.acceleration[1] = float('nan')
            trajectory_msg.acceleration[2] = float('nan')
            trajectory_msg.yaw = float('nan')
            trajectory_msg.yawspeed = self.yaw

            self.publisher_trajectory.publish(trajectory_msg)

            # print("Velocity: ", self.velocity)
            # self.get_logger().error('Current commanded velocity: %s' % self.velocity)
            # self.get_logger().error('Current commanded yaw rate: %s' % self.yaw)



def main(args=None):
    rclpy.init(args=args)

    offboard_control = OffboardControl()

    rclpy.spin(offboard_control)

    offboard_control.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()