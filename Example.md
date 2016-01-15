# TicTacToe #
The following page provides an example of the TicTacToe game implementation using the python statechart library

# Getting the library code #
```
  svn checkout https://pystatecharts.googlecode.com/svn/branches/0.2 src
```

  * The python package for the statechart library will located at src/pystatecharts
  * The source for the tictactoe game can be found at src/tictactoe.py
  * NOTE: In order to successfully run the example, you need the python tkinter package installed with multi-threading enabled. If multi-threading is not enabled for the installed tkinter package, you will need to use the [mtTkinter](http://tkinter.unpythonic.net/wiki/mtTkinter) package. This can be done by copying the mtTkinter.py in the src directory.

# Statechart #

> ![http://lh4.ggpht.com/_YajBMQAFVhU/TI54kH01JfI/AAAAAAAAEJ8/JKedcUBLfuE/s720/tictactoe.png](http://lh4.ggpht.com/_YajBMQAFVhU/TI54kH01JfI/AAAAAAAAEJ8/JKedcUBLfuE/s720/tictactoe.png)

# Implementation #

The statechart consists of
  * A Concurrent State called **Board** having two Hierarchical State Machines (HSM)
    * **Interaction** : Responsible for game interaction with user
    * **Help** : Responsible for help interaction and which can run in parallel with the game interaction machine

The following code listing gives an idea about how the above state chart can be implemented using the python package.

#### Concurrent Board State ####
```
        start = StartState(self)
        end_state = EndState(self)
        BoardState = ConcurrentState(self, None, None, None)

        Transition(start, BoardState, None, None, None)
        Transition(BoardState, end_state, Event(TicTacToeEvent.exit), 
                None, ExitAction())

```

#### Interaction HSM ####
```
        InteractionState = HierarchicalState(BoardState, None, None, None)

        start = StartState(InteractionState)
        PlayState = HierarchicalState(InteractionState, 
                                PlayEntryAction(), None, None)
        DoneState = State(InteractionState, DoneEntryAction(), None, None)

        Transition(start, PlayState, None, None, None)
        Transition(PlayState, DoneState, Event(TicTacToeEvent.game_over), 
                    None, None)
        Transition(DoneState, PlayState, Event(TicTacToeEvent.replay), 
                    None, None)

        start = StartState(PlayState)
        WaitUserInputState = State(PlayState, CheckBoardAction(), None, None) 
        DecideMoveState = State(PlayState, CheckBoardAction(), 
                                MakeMoveAction(), None) 

        Transition(start, WaitUserInputState, None, None, None) 
        Transition(WaitUserInputState, DecideMoveState,
                    Event(TicTacToeEvent.cell_clicked), None, None)
        Transition(DecideMoveState, WaitUserInputState, 
                Event(TicTacToeEvent.move_made), None, None) 
```

#### Help HSM ####
```
        HelpState = HierarchicalState(BoardState, None, None, None)

        start = StartState(HelpState) 
        NoHelpState = State(HelpState, None, None, None)
        ShowHelpState = State(HelpState, ShowHelpEntryAction(), None, None)

        Transition(start, NoHelpState, None, None, None)
        Transition(NoHelpState, ShowHelpState,
                Event(TicTacToeEvent.show_help), None, DisplayHelpAction())
        Transition(ShowHelpState, NoHelpState,
                Event(TicTacToeEvent.dismiss_help), None, NoHelpAction())

```

  * Each of the states (except the start and end states) in the statechart can be associated with the following **action** objects.
    * Entry Action : Executed when the state is entered
    * Do Action : Executed after the entry action
    * Exit Action : Executed when the state is exited
#### Example ####
```
class ShowHelpEntryAction(Action):

    def execute(self, param):
        if param.ui.is_game_over():
            param.ui.showhelp()
```

  * In addition each of the transition in the statechart can be associated with an action object as well.

#### Example ####
```
class ExitAction(Action):

    def execute(self, param):
        param.shutdown()

```
