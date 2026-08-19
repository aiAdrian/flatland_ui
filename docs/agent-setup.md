# Agent Setup

## Tree search

The entire algorithem is absed on a tree search. TThe simulation starts with the trains beeing in their starting positions. But we do not concider those decision points, so All trains will move along the track they are on towards the first decision point. When the first Train reaches the first decision point, the state of the network, is the root node of the state graph.
We then have in this node a number of possible actions that can happen depending what kind of a decision node the trains arrived two. They could decide to wait, or to take a path, left, or right, etc. We then need to create all possible combinations for all the trains that are in a dicision point. So if two trains arrived at a decision point, one at a waiting point and one at a split left or straight, Then we would get [(wait 0, straight), (wait 0, left), (wait 1, straight),(wait 1, left)...]. We then create a branch in the tree for each decision with a new node the new node is what will happen if the given decision is made(So for example the first trains does not wait and the second train goes left) we then forward the simulation until the next train reaches a decision point and the state of that time step becomes the next node on that branch. We do that for all the banches for all the actions. We then pick one of the not yet explored branches and do the same process again for the state note of that branch. We then continu this untill we decide to end the tree search.

Note here that the way the state for the node is beeing created is by moving all trains that are currently traveling between two decision nodes to the next decision node on their way- only for representation puposes!!!. This is simply the case So the observation can be build from the state effectively. The train still has to finish its timesteps to the decision point to make a decision! This is just for the representation to the evaluation agents! We are doing this so the agents only have to learn states that can be represented in the reduced decision graph and not an entire flatland environment.

## Node evaluation

In order to decide which node with be expanded next, we need to eevaluate them. For this we use Neural networks. The NN are trained given the incomplete states of we find in the state notes of the tree and evaluate them. No shortest path, no other compleation for anything. Just the raw evaluation of the current note state. Each network will give out a value for the metric they were trained to predict and the value of a node is the weighted sum of those values. The weighting comes from the user inputed values.

## Network training

The Neural networks need to be trained to evaluate how good a node state is, for a specific metrics, not in terms of its own state, but in terms of the potencial that it has to produce a solution optimising the metirc if the graph search continues to pick notes with the highest value.
