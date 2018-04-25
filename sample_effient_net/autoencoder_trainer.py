import pickle
import torch
from autoencoder_model import *
from gridworldv2 import gameEnv

import torchvision.transforms as transforms
import logger
import pdb
import random
from collections import deque
import shutil

class Memory(object):

    def __init__(self, memory_size=100, burn_in=10):

        self.memory = deque(maxlen=memory_size)

    def sample_batch(self, batch_size, trace_length):

        sampled_episodes = random.sample(self.memory, batch_size)
        sampledTraces = []
        for episode in sampled_episodes:
            point = np.random.randint(0, len(episode)-trace_length)
            sampledTraces.append(episode[point:point+trace_length])
        ## 5 for curr_state, action, reward, isTerminal
        ## Why 5th one? - next state
        ## seems next state, but do I need next state?

        return sampledTraces

        # return random.sample(self.replay, batch_size)

    def append(self, episode):

        self.memory.append(episode)
        ## one transition is one full episode

class Agent():

    def __init__(self):
        self.env_size = 64
        self.env = gameEnv(partial=False, size=self.env_size)
        self.max_epLength = 100
        self.num_episodes = 200
        self.nS = 81
        self.batch_size = 32
        self.trace_length = 5
        self.lr = 1e-4
        self.model = PredictorNet()
        self.model.cuda()
        self.criterion = nn.MultiLabelSoftMarginLoss().cuda()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        self.tb_folder = './pred_autoenc_0/'
        shutil.rmtree(self.tb_folder, ignore_errors=True)
        self.tb = logger.Logger(self.tb_folder, name='freeloc')
        self.model_file = './pred_auto_model_0'
        self.global_step = 0
        self.memory = Memory()

    def train(self):
        self.model.train()
        sigmoid = nn.Sigmoid()

        for n in range(0, self.num_episodes):
            print('Episode:', n)
            ep_state_list = []
            ep_action_list = []
            ep_nextState_list = []
            s = self.env.reset()
            s = s.transpose((2,0,1))
            for j in range(0, self.max_epLength):
                ep_state_list.append(s)
                a = np.random.randint(0, 5)
                ep_action_list.append(a)
                ns, r, d = self.env.step(a)
                ns = ns.transpose((2,0,1))
                ep_nextState_list.append(ns)
                s = ns
            ep_state_arr = np.array(ep_state_list)
            ep_action_arr = np.array(ep_action_list)
            ep_nextState_arr = np.array(ep_nextState_list)
            episode_buffer = zip(ep_state_arr, ep_action_arr, ep_nextState_arr)
            self.memory.append(episode_buffer)

            if n>=self.batch_size:
                # This is a list of batch_size lists each having trace_len tuples
                train_data = self.memory.sample_batch(self.batch_size, self.trace_length)
                batch_s = []
                batch_a = []
                batch_ns = []
                for ep_data in train_data:
                    states = []
                    actions = []
                    for frames_data in ep_data:
                        states.append(frames_data[0])
                        actions.append(frames_data[1])


                    states = np.vstack(states)
                    actions = np.vstack(actions).reshape(-1,)
                    input_states = states[:12]
                    input_actions = actions[:12]
                    target_states = states[12:]
                    batch_s.append(input_states)
                    batch_a.append(input_actions)
                    batch_ns.append(target_states)
                batch_s = np.array(batch_s)
                batch_a = np.array(batch_a)
                batch_ns = np.array(batch_ns)

                batch_s = torch.from_numpy(batch_s).type(torch.FloatTensor).cuda(async=True)
                batch_a = torch.from_numpy(batch_a).type(torch.FloatTensor).cuda(async=True)
                batch_ns = torch.from_numpy(batch_ns).type(torch.FloatTensor).cuda(async=True)
                batch_s = torch.autograd.Variable(batch_s)
                batch_a = torch.autograd.Variable(batch_a)
                batch_ns = torch.autograd.Variable(batch_ns)

                self.optimizer.zero_grad()
                preds = self.model.forward(batch_s, batch_a)
                loss = self.criterion(preds, batch_ns)
                loss.backward()

                self.optimizer.step()
                preds = sigmoid(preds)
                preds = preds >= 0.2
                preds = preds.data.cpu().numpy()
                batch_ns = batch_ns.data.cpu().numpy()
                accuracy = np.sum(preds == batch_ns)*1.0 / (self.batch_size * 3 * self.env_size * self.env_size)
                self.tb.scalar_summary('train/acc', accuracy, self.global_step)
                self.tb.scalar_summary('train/loss', loss, self.global_step)
                self.global_step += 1

        self.save_model_weights()

                # Take only obstacle frame
            #         x1 = x1[:,:,:,0].reshape(-1,81)
            #         x2 = x2[:,:,:,0].reshape(-1,81)
            #         targets = targets[:,:,:,0].reshape(-1,81)
            #         x1 = torch.from_numpy(x1).type(torch.FloatTensor).cuda(async=True)
            #         x2 = torch.from_numpy(x2).type(torch.FloatTensor).cuda(async=True)
            #         targets = torch.from_numpy(targets).type(torch.FloatTensor).cuda(async=True)
            #         x1 = torch.autograd.Variable(x1)
            #         x2 = torch.autograd.Variable(x2)
            #         targets = torch.autograd.Variable(targets)
            #
            #         self.optimizer.zero_grad()
            #         preds = self.model.forward(x1, x2)
            #         loss = self.criterion(preds, targets)
            #         loss.backward()
            #
            #         self.optimizer.step()
            #
            #         accuracy = torch.sum(preds == targets).data.type(torch.FloatTensor) / self.batch_size * 81
            #         self.tb.scalar_summary('train/acc', accuracy, self.global_step)
            #         self.tb.scalar_summary('train/loss', loss, self.global_step)
            #         self.global_step += 1
            # self.save_model_weights()





        #     prevStates, actions, curStates = self.generate_training_data()
        #     nextStates = curStates[1:]
        #     prevStates = prevStates[:-1]
        #     curStates = curStates[:-1]
        #
        #
        #     c = list(zip(prevStates, actions, curStates, nextStates))
        #     random.shuffle(c)
        #     prevStates, actions, curStates, nextStates = zip(*c)
        #     iters = len(prevStates)
        #     for i in range(iters//self.batch_size):
        #         x1 = prevStates[self.batch_size*i:i*self.batch_size+self.batch_size]
        #         x2 = curStates[self.batch_size*i:i*self.batch_size+self.batch_size]
        #         targets = nextStates[self.batch_size*i:i*self.batch_size+self.batch_size]
        #         # Concatenate along 3rd dimension
        #         x1 = np.stack(x1, axis=3)
        #         x2 = np.stack(x2, axis=3)
        #         targets = np.stack(targets, axis=3)
        #         # Transpose to have batchsize at first dim
        #         x1 = np.transpose(x1, (3,0,1,2))
        #         x2 = np.transpose(x2, (3, 0, 1, 2))
        #         targets = np.transpose(targets, (3, 0, 1, 2))
        #         # Take only obstacle frame
        #         x1 = x1[:,:,:,0].reshape(-1,81)
        #         x2 = x2[:,:,:,0].reshape(-1,81)
        #         targets = targets[:,:,:,0].reshape(-1,81)
        #         x1 = torch.from_numpy(x1).type(torch.FloatTensor).cuda(async=True)
        #         x2 = torch.from_numpy(x2).type(torch.FloatTensor).cuda(async=True)
        #         targets = torch.from_numpy(targets).type(torch.FloatTensor).cuda(async=True)
        #         x1 = torch.autograd.Variable(x1)
        #         x2 = torch.autograd.Variable(x2)
        #         targets = torch.autograd.Variable(targets)
        #
        #         self.optimizer.zero_grad()
        #         preds = self.model.forward(x1, x2)
        #         loss = self.criterion(preds, targets)
        #         loss.backward()
        #
        #         self.optimizer.step()
        #
        #         accuracy = torch.sum(preds == targets).data.type(torch.FloatTensor) / self.batch_size * 81
        #         self.tb.scalar_summary('train/acc', accuracy, self.global_step)
        #         self.tb.scalar_summary('train/loss', loss, self.global_step)
        #         self.global_step += 1
        # self.save_model_weights()


    def save_model_weights(self):
        torch.save(self.model.state_dict(), self.model_file)



    def load_model_weights(self):
        checkpoint_dict = torch.load(self.model_file)
        self.model.load_state_dict(checkpoint_dict)



    def test(self):
        self.load_model_weights()
        self.model.eval()
        sum_acc = 0
        count_acc = 0
        sigmoid = nn.Sigmoid()
        for n in range(0, self.num_episodes):
            ep_state_list = []
            ep_action_list = []
            ep_nextState_list = []
            s = self.env.reset()
            s = s.transpose((2,0,1))
            for j in range(0, self.max_epLength):
                ep_state_list.append(s)
                a = np.random.randint(0, 5)
                ep_action_list.append(a)
                ns, r, d = self.env.step(a)
                ns = ns.transpose((2,0,1))
                ep_nextState_list.append(ns)
                s = ns
            ep_state_arr = np.array(ep_state_list)
            ep_action_arr = np.array(ep_action_list)
            ep_nextState_arr = np.array(ep_nextState_list)
            episode_buffer = zip(ep_state_arr, ep_action_arr, ep_nextState_arr)
            self.memory.append(episode_buffer)

            if n>=self.batch_size:
                # This is a list of batch_size lists each having trace_len tuples
                train_data = self.memory.sample_batch(self.batch_size, self.trace_length)
                batch_s = []
                batch_a = []
                batch_ns = []
                for ep_data in train_data:
                    states = []
                    actions = []
                    for frames_data in ep_data:
                        states.append(frames_data[0])
                        actions.append(frames_data[1])


                    states = np.vstack(states)
                    actions = np.vstack(actions).reshape(-1,)
                    input_states = states[:12]
                    input_actions = actions[:12]
                    target_states = states[12:]
                    batch_s.append(input_states)
                    batch_a.append(input_actions)
                    batch_ns.append(target_states)
                batch_s = np.array(batch_s)
                batch_a = np.array(batch_a)
                batch_ns = np.array(batch_ns)

                batch_s = torch.from_numpy(batch_s).type(torch.FloatTensor).cuda(async=True)
                batch_a = torch.from_numpy(batch_a).type(torch.FloatTensor).cuda(async=True)
                batch_ns = torch.from_numpy(batch_ns).type(torch.FloatTensor).cuda(async=True)
                batch_s = torch.autograd.Variable(batch_s)
                batch_a = torch.autograd.Variable(batch_a)
                batch_ns = torch.autograd.Variable(batch_ns)

                preds = self.model.forward(batch_s, batch_a)

                preds = sigmoid(preds)
                preds = preds >= 0.2
                preds = preds.data.cpu().numpy()
                batch_ns = batch_ns.data.cpu().numpy()

                accuracy = np.sum(preds == batch_ns)*1.0 / (self.batch_size * 3 * self.env_size * self.env_size)
                # print(nextState.astype(np.int).reshape(9,9))
                sum_acc += accuracy
                count_acc += 1
        print(sum_acc / count_acc)




    # def generate_training_data(self):
    #     # generate data for one episode
    #     states = []
    #     actions = []
    #     nextStates = []
    #
    #     s = self.env.reset()
    #     for n in range(self.num_episodes):
    #         for j in range(0, self.max_epLength):
    #
    #             states.append(s)
    #             a = np.random.randint(0, 5)
    #             actions.append(a)
    #             s1, r, d = self.env.step(a)
    #             nextStates.append(s1)
    #             s = s1
    #
    #         i=0
    #         datacount = 0
    #         while i<self.max_epLength:
    #             if i>=datacount*5:
    #                 datacount+=1
    #                 frames = []
    #                 frames = torch.vstack(frames)
    #                 dataFrames.append
    #             if i<datacount*5:
    #                 frames.append(states[i])
    #                 datacount += 5
    #         for s, a, s1 in zip(states, actions, nextStates):
    #
    #
    #     return states, actions, nextStates


def main():

    agent = Agent()
    # agent.train()
    agent.test()


if __name__ == '__main__':
    main()