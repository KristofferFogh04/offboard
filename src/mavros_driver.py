#!/usr/bin/env python
"""
Created on Fri Sep 16 23:28:53 2016

@author: dennis
"""

import rospy
from mavros_msgs.msg import State, PositionTarget
from sensor_msgs.msg import Imu
from geometry_msgs.msg import PoseStamped, TwistStamped,Vector3Stamped, Vector3
from mavros_msgs.srv import SetMode, SetModeRequest, SetModeResponse, CommandBool, CommandBoolRequest, CommandBoolResponse, CommandTOL, CommandTOLRequest
from tf.transformations import *
import numpy as np
import common_functions as cf


### constant
RATE_STATE = 1 # state rate subscription


### class for mavros subscription ###
class mavros_driver():
    def __init__(self, nh):
        
        
        ### publisher
        # pose
        self._pose_pub = rospy.Publisher('mavros/setpoint_position/local', PoseStamped, queue_size=10)
        self._pose_msg = PoseStamped()

        # vel 
        self._vel_pub =  rospy.Publisher('mavros/setpoint_velocity/cmd_vel', TwistStamped, queue_size=10 )
        self._vel_msg = TwistStamped()

        # acc
        self._accel_pub = rospy.Publisher('mavros/setpoint_accel/accel', Vector3Stamped, queue_size=10)
        self._accel_msg = Vector3Stamped()


        # local raw: send acceleration and yaw
        self._acc_yaw_pub = rospy.Publisher('/mavros/setpoint_raw/local', PositionTarget, queue_size= 10)
        self._acc_yaw_msg = PositionTarget()
        self._acc_yaw_msg.type_mask = 2048 + 32 + 16 + 8 + 4 + 2 + 1  #+ 512
        
        # local raw: send velocity and yaw
        self._vel_yaw_pub = rospy.Publisher('/mavros/setpoint_raw/local', PositionTarget, queue_size= 10)
        self._vel_yaw_msg = PositionTarget()
        self._vel_yaw_msg.type_mask = 1 + 2 + 4 + 64 + 128 + 256 + 2048

        
   
        ### subscriber ###
        # state subscriber 
        self._rate_state = rospy.Rate(RATE_STATE)
        self.current_state = State()
        rospy.Subscriber('/mavros/state', State , self._current_state_cb)
        
        # wait until connection with FCU 
        while not rospy.is_shutdown() and not self.current_state.connected:
            rospy.Rate(20)     
        print 'FCU connection successful'

        
        # subscriber 
        self.local_pose = PoseStamped()
        rospy.Subscriber('/mavros/local_position/pose', PoseStamped, self._local_pose_cb)
        self.local_vel = TwistStamped()
        rospy.Subscriber('/mavros/local_position/velocity', TwistStamped, self._local_vel_cb)
        self.body_acc = Vector3()
        rospy.Subscriber('/mavros/imu/data', Imu, self._body_imu_cb)



        
    ### getters
    
    ## publishers types
    def get_vel_publisher(self):
        return self._vel_pub
    def get_acc_puclisher(self):
        return self._accel_pub
    def get_pose_publisher(self):
        return self._pose_pub
    def get_bezerier_pub(self):
        return self._bezier_pub
    def get_acc_yaw_pub(self):
        return self._acc_yaw_pub
    def get_vel_yaw_pub(self):
        return self._vel_yaw_pub
    ## msgs types
    def get_vel_msg(self):
        return self._vel_msg
    def get_pose_msg(self):
        return self._pose_msg
    def get_acc_msg(self):
        return self._acc_msg
    def get_bezier_msg(self):
        return self._bezier_msg
    def get_acc_yaw_msg(self):
        return self._acc_yaw_msg
    def get_vel_yaw_msg(self):
        return self._vel_yaw_msg
    
        
    ### setters 
    def set_mode(self, mode):
        if not self._current_state.connected:
            print "No FCU connection"
        elif self._current_state.mode == mode:
            print "Already in " + mode + " mode"
        
        else:
            # wait for service
            rospy.wait_for_service("mavros/set_mode")   
            # service client
            set_mode = rospy.ServiceProxy("mavros/set_mode", SetMode)
            # set request object
            req = SetModeRequest()
            req.custom_mode = mode
            # zero time 
            t0 = rospy.get_time()
            
            # check response
            while not rospy.is_shutdown() and (self.current_state.mode != req.custom_mode):
                if rospy.get_time() - t0 > 2.0: # check every 5 seconds
                
                    try:
                        # request 
                        set_mode.call(req)
                        
                    except rospy.ServiceException, e:
                        print "Service did not process request: %s"%str(e)
                    t0 = rospy.get_time()
            print "Mode: "+self.current_state.mode + " established"

    
    
    
    
    def arm(self, do_arming):
        
        if self.current_state.armed and do_arming:
            print "already armed" 
        else:
            # wait for service
            rospy.wait_for_service("mavros/cmd/arming")   
        
            # service client
            set_arm = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)
            
            # set request object
            req = CommandBoolRequest()
            req.value = do_arming
            
             # zero time 
            t0 = rospy.get_time()

            # check response
            if do_arming:
                while not rospy.is_shutdown() and not self.current_state.armed:
                    if rospy.get_time() - t0 > 2.0: # check every 5 seconds
                    
                        try:
                            # request 
                            set_arm.call(req)
                            
                        except rospy.ServiceException, e:
                            print "Service did not process request: %s"%str(e)
      
                        t0 = rospy.get_time()
                
                print "armed: ", self.current_state.armed
                
            else: 
                while not rospy.is_shutdown() and self.current_state.armed:
                    if rospy.get_time() - t0 > 0.5: # check every 5 seconds
                    
                        try:
                            # request 
                            set_arm.call(req)
                            
                        except rospy.ServiceException, e:
                            print "Service did not process request: %s"%str(e)
      
                        t0 = rospy.get_time()
                    
                
            
    def land(self):
        
        if not self.current_state.armed:
            print "not armed yet"
        else:
            
            # wait for service
            rospy.wait_for_service("mavros/cmd/land")   
            
            # service client
            set_rq = rospy.ServiceProxy("mavros/cmd/land", CommandTOL)
            
            # set request object
            req = CommandTOLRequest()
            req.yaw = 0.0
            req.latitude = 0.0
            req.longitude = 0.0
            req.altitude = 0.0
            req.min_pitch = 0.0
            
            #zero time 
            t0 = rospy.get_time()
            
            # check response
            while self.current_state.armed:
                if rospy.get_time() - t0 > 5.0: # check every 5 seconds
                
                    try:
                        # request 
                        set_rq.call(req)
                        
                    except rospy.ServiceException, e:
                        print "Service did not process request: %s"%str(e)
                    t0 = rospy.get_time()
                       
            print "landed savely"
            
            
        
    ### callback functions ###
    def _current_state_cb(self, data):
        self.current_state = data

    def _local_pose_cb(self, data):
        self.local_pose = data
        
    def _local_vel_cb(self, data):
        self.local_vel = data
        
    def _body_imu_cb(self, data):
        self.body_acc = data



  