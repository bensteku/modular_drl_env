import gym
import numpy as np
import pybullet as pyb
from time import time

# import abstracts
from robot.robot import Robot
from sensor.sensor import Sensor
from goal.goal import Goal
from world.world import World

# import implementations, new ones hav to be added here
#   worlds
from world.random_obstacles import RandomObstacleWorld
#   robots
from robot.ur5 import UR5
#   sensors
from sensor.joints_sensor import JointsSensor
from sensor.position_and_rotation_sensor import PositionRotationSensor
from sensor.lidar import LidarSensorUR5
#   goals
from goal.position_collision import PositionCollisionGoal

class ModularDRLEnv(gym.Env):

    def __init__(self, env_config):

        # here the parser for the env_config (a python dict for the external YAML file) will appear at some point
        # for now, the attributes needed to get this prototype to run are set manually here
        
        # general env attributes
        self.normalize_observations = env_config["normalize_observations"]
        self.normalize_rewards = env_config["normalize_rewards"]
        self.display = env_config["display"]
        self.show_auxillary_geometry_world = env_config["display_extra"]
        self.show_auxillary_geometry_goal = env_config["display_extra"]
        self.train = env_config["train"]
        self.max_steps_per_episode = 1024
        self.logging = env_config["logging"]  # 0:no logging, 1:logging for console, 2: logging for console and to text file after each episode
        self.stat_buffer_size = 25  # length of the stat arrays in terms of episodes over which the average will be drawn for logging
        self.sim_step = 1 / 240  # in seconds -> 240 Hz

        # tracking variables
        self.steps_current_episode = 0
        self.sim_time = 0
        self.cpu_time = 0
        self.cpu_epoch = time()
        self.log = []
        self.success_stat = [False]
        self.out_of_bounds_stat = [False]
        self.timeout_stat = [False]
        self.collision_stat = [False]
        self.goal_metrics = []
        self.reward = 0
        self.reward_cumulative = 0

        # world attributes
        workspace_boundaries = [-0.4, 0.4, 0.3, 0.7, 0.2, 0.5]
        robot_base_positions = [np.array([0.0, -0.12, 0.5]), np.array([0.0, 1.12, 0.5])]
        robot_base_orientations = [np.array([0, 0, 0, 1]), np.array([0, 0, 0, 1])]
        num_static_obstacles = 3
        num_moving_obstacles = 1
        box_measurements = [0.025, 0.075, 0.025, 0.075, 0.00075, 0.00125]
        sphere_measurements = [0.005, 0.02]
        moving_obstacles_vels = [0.0015, 0.005]
        #moving_obstacles_vels = [0.2, 0.2]
        moving_obstacles_directions = []
        moving_obstacles_trajectory_length = [1, 3]

        # robot attributes
        self.xyz_vels = [0.005]
        self.rpy_vels = [0.005]
        self.joint_vels = [0.015]
        self.joint_control = [env_config["joint_control"]]

        # set up the PyBullet client
        disp = pyb.DIRECT if not self.display else pyb.GUI
        pyb.connect(disp)
        pyb.setAdditionalSearchPath("./assets/")
        
        self.world = RandomObstacleWorld(workspace_boundaries=workspace_boundaries,
                                         robot_base_positions=robot_base_positions,
                                         robot_base_orientations=robot_base_orientations,
                                         num_static_obstacles=num_static_obstacles,
                                         num_moving_obstacles=num_moving_obstacles,
                                         box_measurements=box_measurements,
                                         sphere_measurements=sphere_measurements,
                                         moving_obstacles_vels=moving_obstacles_vels,
                                         moving_obstacles_directions=moving_obstacles_directions,
                                         moving_obstacles_trajectory_length=moving_obstacles_trajectory_length)

        # at this point robots would dynamically be created as needed by the config/the world
        # however, for now we generate one manually
        self.robots = []
        ur5_1 = UR5(name="ur5_1", 
                   world=self.world,
                   base_position=robot_base_positions[0],
                   base_orientation=robot_base_orientations[0],
                   resting_angles=np.array([np.pi/2, -np.pi/6, -2*np.pi/3, -4*np.pi/9, np.pi/2, 0.0]),
                   end_effector_link_id=7,
                   base_link_id=1,
                   control_joints=self.joint_control[0],
                   xyz_vel=self.xyz_vels[0],
                   rpy_vel=self.rpy_vels[0],
                   joint_vel=self.joint_vels[0])
        self.robots.append(ur5_1)
        ur5_1.id = 1

        # at this point we would generate all the sensors prescribed by the config for each robot and assign them to the robots
        # however, for now we simply generate the two necessary ones manually
        self.sensors = []
        ur5_1_position_sensor = PositionRotationSensor(self.normalize_observations, True, True, self.sim_step, ur5_1, 7)
        ur5_1_joint_sensor = JointsSensor(self.normalize_observations, True, True, self.sim_step, ur5_1)
        ur5_1.set_joint_sensor(ur5_1_joint_sensor)
        ur5_1.set_position_rotation_sensor(ur5_1_position_sensor)

        ur5_1_lidar_sensor = LidarSensorUR5(normalize=self.normalize_observations,
                                            add_to_observation_space=True, 
                                            add_to_logging=False,
                                            sim_step=self.sim_step,
                                            robot=ur5_1, 
                                            indicator_buckets=9,
                                            ray_start=0,
                                            ray_end=0.3,
                                            num_rays_side=10,
                                            num_rays_circle_directions=6,
                                            render=False,
                                            indicator=True)

        self.sensors = [ur5_1_joint_sensor, ur5_1_position_sensor, ur5_1_lidar_sensor]


        # at this point we would generate all the goals needed and assign them to their respective robots
        # however, for the moment we simply generate the one we want for testing
        self.goals = []
        ur5_1_goal = PositionCollisionGoal(robot=ur5_1,
                                           normalize_rewards=self.normalize_rewards,
                                           normalize_observations=self.normalize_observations,
                                           train=self.train,
                                           add_to_logging=True,
                                           max_steps=self.max_steps_per_episode,
                                           continue_after_success=False, 
                                           reward_success=10,
                                           reward_collision=-10,
                                           reward_distance_mult=-0.01,
                                           dist_threshold_start=0.2,
                                           dist_threshold_end=0.01,
                                           dist_threshold_increment_start=0.01,
                                           dist_threshold_increment_end=0.001)
        self.goals.append(ur5_1_goal)
        ur5_1.set_goal(ur5_1_goal)

        self.world.register_robots(self.robots)

        # construct observation space from sensors and goals
        # each sensor and goal will add elements to the observation space with fitting names
        observation_space_dict = dict()
        for sensor in self.sensors:
            if sensor.add_to_observation_space:
                observation_space_dict = {**observation_space_dict, **sensor.get_observation_space_element()}  # merges the two dicts
        for goal in self.goals:
            if goal.add_to_observation_space:
                observation_space_dict = {**observation_space_dict, **goal.get_observation_space_element()}

        self.observation_space = gym.spaces.Dict(observation_space_dict)

        # construct action space from robots
        # the action space will be a vector with the length of all robot's control dimensions added up
        # e.g. if one robot needs 4 values for its control and another 10,
        # the action space will be a 10-vector with the first 4 elements working for robot 1 and the last 6 for robot 2
        self.action_space_dims = []
        for idx, robot in enumerate(self.robots):
            ik_dims, joints_dims = robot.get_action_space_dims()
            if self.joint_control[idx]:
                self.action_space_dims.append(joints_dims)
            else:
                self.action_space_dims.append(ik_dims)
        
        self.action_space = gym.spaces.Box(low=-1, high=1, shape=(sum(self.action_space_dims),), dtype=np.float32)

    def reset(self):
        # disable rendering for the setup to save time
        pyb.configureDebugVisualizer(pyb.COV_ENABLE_RENDERING, 0)

        # reset the tracking variables
        self.steps_current_episode = 0
        self.log = []
        self.sim_time = 0
        self.cpu_time = 0
        self.cpu_epoch = time()
        self.reward = 0
        self.reward_cumulative = 0

        # build the world and robots
        # this is put into a loop that will only break if the generation process results in a collision free setup
        # the code will abort if even after several attempts no valid starting setup is found
        # TODO: maybe find a smarter way to do this
        reset_count = 0
        while True:
            if reset_count > 1000:
                raise Exception("Could not find collision-free starting setup after 1000 tries. Maybe check your world generation code.")

            # reset PyBullet
            pyb.resetSimulation()

            # reset world attributes
            self.world.reset()

            # spawn robots in world
            for robot in self.robots:
                robot.build()

            # get a set of starting positions for the end effectors
            ee_starting_points = self.world.create_ee_starting_points()
            
            # get position and roation goals
            position_targets = self.world.create_position_target()
            rotation_targets = self.world.create_rotation_target()

            # spawn world objects
            self.world.build()

            # set the robots into the starting positions
            for idx, ee_pos in enumerate(ee_starting_points):
                if ee_pos[0] is None:
                    continue  # nothing to do here
                elif ee_pos[1] is None:
                    # only position
                    self.robots[idx].moveto_xyz(ee_pos[0])
                else:
                    # both position and rotation
                    self.robots[idx].moveto_xyzquat(ee_pos[0], ee_pos[1])
            
            # check collision
            self.world.perform_collision_check()
            if not self.world.collision:
                break
            else:
                reset_count += 1

        # set all robots to active
        self.active_robots = [True for robot in self.robots]

        # reset the sensors to start settings
        for sensor in self.sensors:
            sensor.reset()

        # call the goals' update routine and get their metrics, if they exist
        self.goal_metrics = []
        for goal in self.goals:
            self.goal_metrics.append(goal.on_env_reset(np.average(self.success_stat)))

        # render non-essential visual stuff
        if self.show_auxillary_geometry_world:
            self.world.build_visual_aux()
        if self.show_auxillary_geometry_goal:
            for goal in self.goals:
                goal.build_visual_aux()

        # turn rendering back on
        pyb.configureDebugVisualizer(pyb.COV_ENABLE_RENDERING, 1)

        return self._get_obs()

    def _get_obs(self):
        obs_dict = dict()
        # get the sensor data
        for sensor in self.sensors:
            if sensor.add_to_observation_space:
                obs_dict = {**obs_dict, **sensor.get_observation()}
        for goal in self.goals:
            if goal.add_to_observation_space:
                obs_dict = {**obs_dict, **goal.get_observation()}

        # no normalizing here, that should be handled by the sensors and goals

        return obs_dict

    def step(self, action):
        
        # convert to numpy
        action = np.array(action)
        
        # update world
        self.world.update()

        # apply the action to all robots that have to be moved
        offset = 0  # the offset at which the ith robot sits in the action array
        exec_times_cpu = []  # track execution times
        for idx, robot in enumerate(self.robots):
            if not self.active_robots[idx]:
                continue
            current_robot_action = action[offset : self.action_space_dims[idx] + offset]
            offset += self.action_space_dims[idx]
            exec_time = robot.process_action(current_robot_action)
            exec_times_cpu.append(exec_time)

        # update the sensor data
        for sensor in self.sensors:
            sensor.update()

        # update the collision model
        self.world.perform_collision_check()

        # calculate reward and get termination conditions
        rewards = []
        dones = []
        successes = []
        timeouts = []
        oobs = []
        for idx, goal in enumerate(self.goals):
            reward_info = goal.reward(self.steps_current_episode)  # tuple: reward, success, done
            rewards.append(reward_info[0])
            successes.append(reward_info[1])
            # set respective robot to inactive after success, if needed
            if reward_info[1] and not goal.continue_after_success:
                self.active_robots[idx] = False
            dones.append(reward_info[2])
            timeouts.append(reward_info[3])
            oobs.append(reward_info[4])

        # determine overall env termination condition
        collision = self.world.collision
        done = np.any(dones) or collision  # one done out of all goals/robots suffices for the entire env to be done or anything collided
        is_success = np.all(successes)  # all goals must be succesful for the entire env to be
        timeout = np.any(timeouts)
        out_of_bounds = np.any(oobs)

        # reward
        # if we are normalizing the reward, we must also account for the number of robots 
        # (each goal will output a reward from -1 to 1, so e.g. three robots would have a cumulative reward range from -3 to 3)
        if self.normalize_rewards:
            self.reward = np.average(rewards)
        # otherwise we can just add the single rewards up
        else:
            self.reward = np.sum(rewards)
        self.reward_cumulative += self.reward

        # update tracking variables and stats
        self.sim_time += self.sim_step
        self.cpu_time = time() - self.cpu_epoch
        self.steps_current_episode += 1
        if done:
            self.success_stat.append(is_success)
            if len(self.success_stat) > self.stat_buffer_size:
                self.success_stat.pop(0)
            self.timeout_stat.append(timeout)
            if len(self.timeout_stat) > self.stat_buffer_size:
                self.timeout_stat.pop(0)
            self.out_of_bounds_stat.append(out_of_bounds)
            if len(self.out_of_bounds_stat) > self.stat_buffer_size:
                self.out_of_bounds_stat.pop(0)
            self.collision_stat.append(collision)
            if len(self.collision_stat) > self.stat_buffer_size:
                self.collision_stat.pop(0)

        if self.logging == 0:
            # no logging
            info = {}
        if self.logging == 1 or self.logging == 2:
            # logging to console or textfile

            # start log dict with env wide information
            info = {"is_success": is_success, 
                    "step": self.steps_current_episode,
                    "success_rate": np.average(self.success_stat),
                    "out_of_bounds_rate": np.average(self.out_of_bounds_stat),
                    "timeout_rate": np.average(self.timeout_stat),
                    "collision_rate": np.average(self.collision_stat),
                    "sim_time": self.sim_time,
                    "cpu_time": self.cpu_time}
            # get robot execution times
            for idx, robot in enumerate(self.robots):
                info["action_cpu_time_" + robot.name] = exec_times_cpu[idx] 
            # get the log data from sensors
            for sensor in self.sensors:
                if sensor.add_to_logging:
                    info = {**info, **sensor.get_data_for_logging()}
            # get log data from goals
            for goal in self.goals:
                if goal.add_to_logging:
                    info = {**info, **goal.get_data_for_logging()}

            self.log.append(info)

            # on episode end:
            if done:
                # write to console
                info_string = self._get_info_string(info)
                print(info_string)
                # write to textfile, in this case the entire log so far
                if self.logging == 2:
                    with open("./test.txt", "w") as outfile:
                        for line in self.log:
                            info_string = self._get_info_string(line)
                            outfile.write(info_string+"\n")

        return self._get_obs(), self.reward, done, info

    def _get_info_string(self, info):
        """
        Handles writing info from sensors and goals to console. Also deals with various datatypes and should be updated
        if a new one appears in the code somewhere.
        """
        info_string = ""
        for key in info:
            # handle a few common datatypes and special cases
            if type(info[key]) == np.ndarray:
                to_print = ""
                for ele in info[key]:
                    to_print += str(round(ele, 3)) + " "
                to_print = to_print[:-1]  # cut off the last space
            elif type(info[key]) == np.bool_ or type(info[key]) == bool:
                to_print = str(int(info[key]))
            elif "time" in key:
                if info[key] > 0.01:  # time not very small
                    to_print = str(round(info[key], 3))
                else:  # time very small
                    to_print = "{:.2e}".format(info[key])
            else:
                to_print = str(round(info[key], 3))
            info_string += key + ": " + to_print + ", "
        return info_string[:-1]  # cut off last space