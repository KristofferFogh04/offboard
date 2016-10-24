#!/usr/bin/env python
"""
Created on Fri Sep 16 23:28:53 2016

@author: dennis
"""

import rospy
from mavros_msgs.msg import State, AttitudeTarget, PositionTarget
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseStamped, TwistStamped, Vector3Stamped, Quaternion, Vector3, Point
from nav_msgs.msg import Path
import time
from tf.transformations import *
import numpy as np
import common_functions as cf
import bezier_fn as bf
import pub_bezier


### constant
RATE_STATE = 1 # state rate subscription


### class for subscription ###
class mapping():
    def __init__(self, nh):

    
        ### subscriber ###
        
        # state subscriber 
        self._rate_state = rospy.Rate(RATE_STATE)
        self._current_state = State()
        rospy.Subscriber('/mavros/state', State , self._current_state_cb)
        
        # subscriber,
        self._local_pose = PoseStamped()
        rospy.Subscriber('/mavros/local_position/pose', PoseStamped, self._local_pose_cb)
        self._local_vel = TwistStamped()
        rospy.Subscriber('/mavros/local_position/velocity', TwistStamped, self._local_vel_cb)
        self._bezier_pt = Path()
        rospy.Subscriber('/path/bezier_pt', Path, self._bezier_cb)
        
        
        # vel pub
        self._vel_pub =  rospy.Publisher('mavros/setpoint_velocity/cmd_vel', TwistStamped, queue_size=10 )
        self._vel_msg = TwistStamped()
        

        # acc pub
        self._accel_pub = rospy.Publisher('/mavros/setpoint_accel/accel', Vector3Stamped, queue_size=10 )
        self._accel_msg = Vector3Stamped()
        
        # attitude 
        self._att_pub = rospy.Publisher('/mavros/setpoint_raw/attitude', AttitudeTarget, queue_size=10)
        self._att_msg = AttitudeTarget()
        self._att_msg.type_mask = 7
        
        # local raw: send acceleration and yaw
        self._acc_yaw_pub = rospy.Publisher('/mavros/setpoint_raw/local', PositionTarget, queue_size= 10)
        self._acc_yaw_msg = PositionTarget()
        self._acc_yaw_msg.type_mask = 2048 + 32 + 16 + 8 + 4 + 2 + 1  #+ 512
        
        # local raw: send velocity and yaw
        self._vel_yaw_pub = rospy.Publisher('/mavros/setpoint_raw/local', PositionTarget, queue_size= 10)
        self._vel_yaw_msg = PositionTarget()
        self._vel_yaw_msg.type_mask = 1 + 2 + 4 + 64 + 128 + 256 + 2048
        
        
        # initlaize publisher for visualization
        self._pub_visualize = pub_bezier.pub_bezier()

        

        
    def _pub_att_desired(self):

        
        q = Quaternion()
        q.x =0.0
        q.y = 0.0
        q.z = 1.0
        q.w = 0.0
        
        self._att_msg.orientation = q
        self._att_msg.thrust =1.0
        
        self._att_pub.publish(self._att_msg)
        
        
    def _pub_acc_yaw_desired(self):
        
        a = Vector3()
        a.x = 0.0
        a.y = 0.0
        a.z = 0.2
        self._acc_yaw_msg.acceleration_or_force = a
        #self._local_msg.yaw = 0.0
        
        self._local_pub.publish(self._acc_yaw_msg)
        
        
        
  
    
    def _pub_v_desired(self):
        
        # get current position
        pose = cf.p_ros_to_numpy(self._local_pose.pose.position)
        
        
        bz = [cf.p_ros_to_numpy(self._bezier_pt.poses[0].pose.position), \
                cf.p_ros_to_numpy(self._bezier_pt.poses[1].pose.position), \
                cf.p_ros_to_numpy(self._bezier_pt.poses[2].pose.position)]
        

        # get closest point and velocity to bezier
        p_des, v_des, a_des = bf.point_closest_to_bezier(bz, pose)
        
        # send velocity vector
        self._visualize_vel(p_des, v_des)
        self._visualize_x(pose)
        
        
        # get desired velocity
        v_final = bf.vel_adjusted(p_des, v_des, pose)
        
        # get yaw angle error
        theta = 0.0
        v_des_norm= np.linalg.norm(v_des)
        z = np.array([0.0,0.0,1.0])
        if (v_des_norm > 0.0) and not (np.array_equal(np.abs(v_des/v_des_norm), z)): #yaw not defined if norm(v_des) or v_des == z 
            
            theta = self.angle_error(v_des)
            
        # get current yaw
        yaw_desired = self.get_desired_yaw(v_des) - np.pi/2.0
        
        
        # assign to msg
        self._vel_yaw_msg.velocity = cf.p_numpy_to_ros_vector(v_final)
        self._vel_yaw_msg.yaw = yaw_desired
        
        # publish
        self._vel_yaw_pub.publish(self._vel_yaw_msg)
        
    def _visualize_x(self, pose):
        
        # current orientation
        q_c = cf.q_ros_to_numpy(self._local_pose.pose.orientation)
        
        # body frame x
        x_b = np.array([1.0,0.0,0.0])
        
        # convert to world frame
        x = np.dot(cf.rotation_from_q_transpose(q_c), x_b)
        
        pt = cf.p_numpy_to_ros(pose)
        pt2 = cf.p_numpy_to_ros(pose + x)
        
        pts = [pt, pt2]
        
        
        self._pub_visualize.pub_x_vec(pts)
        
        
      
    def _visualize_vel(self, p, v):
        

        pt = cf.p_numpy_to_ros(p)
        pt2 = cf.p_numpy_to_ros(v + p)
        points = [pt, pt2]

        self._pub_visualize.pub_velocity(points)
        
        
        
        
        
        
        
    def _pub_a_desired(self):
        
        # get current position, velocity
        pose = cf.p_ros_to_numpy(self._local_pose.pose.position)
        velocity = cf.p_ros_to_numpy(self._local_vel.twist.linear)
        
        
        bz = [cf.p_ros_to_numpy(self._bezier_pt.poses[0].pose.position), \
                cf.p_ros_to_numpy(self._bezier_pt.poses[1].pose.position), \
                cf.p_ros_to_numpy(self._bezier_pt.poses[2].pose.position)]
        

        # get closest point and velocity and acceleration to bezier
        p_des, v_des, a_des = bf.point_closest_to_bezier(bz, pose)
        
        
        # get desired velocity
        a_final = bf.accel_adjusted(p_des, v_des, a_des, pose, velocity)
        
        #print "a_des : {}\t v_des : {}\t p_des: {}".format(a_des, v_des, p_des) 
        
        # get yaw angle error
        '''theta = 0.0
        v_des_norm= np.linalg.norm(v_des)
        z = np.array([0.0,0.0,1.0])
        if (v_des_norm > 0.0) and not (np.array_equal(np.abs(v_des/v_des_norm), z)): #yaw not defined if norm(v_des) or v_des == z 
            
            theta = self.angle_error(v_des)'''
            
        #a_final = np.array([0.0,0.0,0.52])
        
        # assign to msg
        self._accel_msg.vector = cf.p_numpy_to_ros(a_final)

     
        
        # publish
        self._accel_pub.publish(self._accel_msg)
        
        
    
        
        
    # finds closest point on circel to a specific point
    def angle_error(self, v_des):
        
        # current orrientation
        q_c = cf.q_ros_to_numpy(self._local_pose.pose.orientation)
    
        # convert v_des to body frame
        vb_des = np.dot(cf.rotation_from_q(q_c), v_des)
        
        # body z axis x
        z = np.array([0.0,0.0,1.0])
        x = np.array([1.0,0.0,0.0])

        # project onto xy body plane
        vb_des_proj = vb_des - z * np.dot(z, np.transpose(vb_des))
        
        # normalize
        vb_proj_n = vb_des_proj / np.linalg.norm(vb_des_proj)
        
        
        # get angle 
        theta = np.arccos(np.dot(x, np.transpose(vb_proj_n)))
        
        
        # determine sign
        cross = np.cross(x, vb_proj_n)
        if ( cross[2] < 0.0 ):
            theta *= -1.0
            
        #print theta
        
        return theta
        
        
    # get desired yaw   
    def get_desired_yaw(self, v_des):
        
        # z axis
        z = np.array([0.0,0.0,1.0])
        x = np.array([1.0,0.0,0.0])
        
        # project v_des onto xy plane
        v_des_proj = v_des - z * np.dot(z, np.transpose(v_des))
        v_des_p_n = v_des_proj / np.linalg.norm(v_des_proj)
        
        # angle between v_des_prj and x
        angle = np.arccos(np.dot(x, np.transpose(v_des_p_n)))
        
        # sign
        cross = np.cross(x, v_des_p_n)
        if (cross[2] < 0.0):
            angle *= -1
             
        return angle
            
        
        
            
        
    # current yaw
    def get_current_yaw(self):
       
        # current orrientation
        q_c = cf.q_ros_to_numpy(self._local_pose.pose.orientation)
        
        # body frame x
        x_b = np.array([1.0,0.0,0.0])
        
        # convert to world frame
        x_w = np.dot(cf.rotation_from_q_transpose(q_c), x_b)
        
        # norm of xy plane
        z = np.array([0.0,0.0,1.0])
        x = np.array([1.0,0.0,0.0])
        
        # pojecto on xy placne of world frame
        x_w_proj = x_w - z * np.dot(z, np.transpose(x_w))  
        
        # normalize
        x_w_proj_n = x_w_proj / np.linalg.norm(x_w_proj)
        
        # get angle 
        yaw = np.arccos(np.dot(x, np.transpose(x_w_proj_n)))
        
        
        #determine sign
        cross = np.cross(x, x_w_proj_n)
        if (cross[2] < 0.0):
            yaw *= -1.0
            
        return yaw
       
        
    ### callback functions ###
    
    def _current_state_cb(self, data):
        self._current_state = data


    def _local_pose_cb(self, data):
        self._local_pose = data
        
    def _local_vel_cb(self, data):
        self._local_vel = data
        
    def _bezier_cb(self, data):
        self._bezier_pt = data
        self._pub_v_desired()
        
        
        
        




#  node enter point
def main():
    
    # create ros node handle
    nh = rospy.init_node('beziermapping')
    
    # create mapping obj
    mapping(nh)
    
    # spin 
    rospy.spin()
    
if __name__ == '__main__':
    main()