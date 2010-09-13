#!/usr/bin/env python

try:
    from mtTkinter import *
except ImportError:
    print ("Warning: Using standard tkinter. You might have " +
           "problems if tkinter module is not multi thread enabled.")
    from Tkinter import *

import tkMessageBox
import random

from threading import Thread
from threading import Lock 

from pystatecharts.pseudostates import StartState
from pystatecharts.pseudostates import EndState
from pystatecharts.pseudostates import HistoryState
from pystatecharts.states import Statechart
from pystatecharts.states import State
from pystatecharts.states import ConcurrentState
from pystatecharts.states import HierarchicalState  
from pystatecharts.states import Transition 
from pystatecharts.action import Action
from pystatecharts.transition import Event 
from pystatecharts.runtime import RuntimeData

class TicTacToeEvent:
    init_done       = 1
    cell_clicked    = 2
    move_made       = 3
    show_help       = 4
    dismiss_help    = 5
    game_over       = 6
    replay          = 7 
    exit            = 8

class UI:

    def create_menu(self):
        menubar = Menu(self.root)
        options_menu = Menu(menubar)
        options_menu.add_command(label="Help", command = self.showhelp)
        options_menu.add_command(label="Replay", command = self.replay)
        options_menu.add_command(label="Quit", command = self.quit)
        menubar.add_cascade(label="Options", menu=options_menu)
        self.root.config(menu=menubar)

    def create_grid(self):
        self.co_ordinates = {}
        self.buttons = {}

        for r in range(0, 3):
            for c in range(0, 3):
                button = Button(self.frame, text = "_", 
                            disabledforeground = "black")
                button.grid(row = r, column = c) 
                button.bind("<Button-1>", self.user_clicked)
                button.config(relief=SUNKEN)
                self.co_ordinates[button] = (r, c)
                self.buttons[(r, c)] = button

    def create_model(self):
        self.model = [['-' for i in range(0, 3)] for j in range(0, 3)]

    def __init__(self, interface):
        self.interface = interface
        self.root = Tk()
        self.root.resizable(width=FALSE, height=FALSE)
        self.root.title("TTT")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.frame = Frame(self.root)
        self.frame.pack()

    def init_grid(self):
        self.create_grid()
        self.create_model()

    def init(self):
        self.create_menu()
        self.init_grid()

    def kick_off(self):
        self.root.mainloop()

    def shutdown(self):
        self.root.quit()
    
    def showhelp(self):
        self.interface.sendEvent(TicTacToeEvent.show_help)

    def display_help(self): 
        self.help = Toplevel()
        self.help.title("Help for this application...")

        msg = Message(self.help, text="Really?")
        msg.pack()

        button = Button(self.help, text="Dismiss", command=self.help_close)
        button.pack()

    def help_close(self):    
        self.interface.sendEvent(TicTacToeEvent.dismiss_help)

    def dismiss_help(self):

        if self.help:
            self.help.destroy()
            self.help = None

    def user_clicked(self, event):
        if event.widget.cget('state') == 'active':
            event.widget.config(state = 'disabled')
            event.widget.config(text = 'X')
            x, y = self.co_ordinates[event.widget]
            self.model[x][y] = 'X'
            self.interface.sendEvent(TicTacToeEvent.cell_clicked)

    def computer_play(self):
        
        choices = list()
        for row in range(0, 3):
            for col in range(0, 3):
                if self.model[row][col] == "-":
                    choices.append((row, col))

        if len(choices) == 0:
            return

        x, y = random.choice(choices)                     

        button = self.buttons[(x, y)]
        assert button.cget('state') == 'normal',\
            "Button state %s" % button.cget('state')
        button.config(state = 'disabled')
        button.config(text = '0')
        self.model[x][y] = '0'

    def replay(self):
        self.init_grid()
        self.interface.sendEvent(TicTacToeEvent.replay) 

    def quit(self):
        self.interface.sendEvent(TicTacToeEvent.exit) 

    def disable_grid(self):
        for _, button in self.buttons.items():
            button.config(state = 'disabled')                        

    def mark_row(self, row):
        for col in range(0, 3):
            button = self.buttons[(row, col)]
            button.config(disabledforeground = "red")                    

    def mark_column(self, col):
        for row in range(0, 3):
            button = self.buttons[(row, col)]
            button.config(disabledforeground = "red")  
    
    def mark_diagonal(self, co_ords):
        for co_ord in co_ords:
            button = self.buttons[co_ord]
            button.config(disabledforeground = "red")  
           

    def is_game_over(self):

        for sym in ['X', '0']:

            for row in range(0, 3):
                if (self.model[row][0] == sym and
                    self.model[row][1] == sym and
                    self.model[row][2] == sym):
                    self.disable_grid()
                    self.mark_row(row)
                    return True

            for col in range(0, 3):
                 if (self.model[0][col] == sym and
                     self.model[1][col] == sym and
                     self.model[2][col] == sym):
                    self.disable_grid()
                    self.mark_column(col)
                    return True
       
            if (self.model[0][0] == sym and
                self.model[1][1] == sym and
                self.model[2][2] == sym):
                self.disable_grid()
                self.mark_diagonal([(0, 0), (1, 1), (2, 2)])
                return True                    

            if (self.model[0][2] == sym and
                self.model[1][1] == sym and
                self.model[2][0] == sym):
                self.disable_grid()
                self.mark_diagonal([(0, 2), (1, 1), (2, 0)])
                return True                    

        for row in range(0, 3):
            for col in range(0, 3):
                if self.model[row][col] == "-":
                    return False

        self.disable_grid()
        return True 

class PlayEntryAction(Action):

    def execute(self, param):
        param.ui.init()
        param.sendEvent(TicTacToeEvent.init_done) 

class CheckBoardAction(Action):

    def execute(self, param):
        if param.ui.is_game_over():
            param.sendEvent(TicTacToeEvent.game_over)

class ShowHelpEntryAction(Action):

    def execute(self, param):
        if param.ui.is_game_over():
            param.ui.showhelp()

class MakeMoveAction(Action):

    def execute(self, param):
        if param.ui.is_game_over():
            param.sendEvent(TicTacToeEvent.game_over)
        else:
            param.ui.computer_play()  
            param.sendEvent(TicTacToeEvent.move_made) 

class DoneEntryAction(Action):

    def execute(self, param):
        if tkMessageBox.askyesno("Replay", "Start a new game ?"):
            param.ui.init_grid()
            param.sendEvent(TicTacToeEvent.replay) 

class ExitAction(Action):

    def execute(self, param):
        param.shutdown()

class DisplayHelpAction(Action):
    
    def execute(self, param):
        param.ui.display_help()

class NoHelpAction(Action):
    
    def execute(self, param):
        param.ui.dismiss_help()

class TicTacToeStatechart(Statechart):

    def __init__(self, param):
        Statechart.__init__(self, param)

        start = StartState(self)
        end_state = EndState(self)
        BoardState = ConcurrentState(self, None, None, None)

        Transition(start, BoardState, None, None, None)
        Transition(BoardState, end_state, Event(TicTacToeEvent.exit), 
                None, ExitAction())

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
     
        HelpState = HierarchicalState(BoardState, None, None, None)

        start = StartState(HelpState) 
        NoHelpState = State(HelpState, None, None, None)
        ShowHelpState = State(HelpState, ShowHelpEntryAction(), None, None)

        Transition(start, NoHelpState, None, None, None)
        Transition(NoHelpState, ShowHelpState, 
                Event(TicTacToeEvent.show_help), None, DisplayHelpAction())
        Transition(ShowHelpState, NoHelpState, 
                Event(TicTacToeEvent.dismiss_help), None, NoHelpAction())
        
class StatechartThread(Thread):

    def __init__(self, interface):
        Thread.__init__(self)
        self.interface = interface 
        self.running = False

    def run(self):
        
        interface = self.interface
        self.running = True

        while self.running:
            event = None

            interface.lock.acquire()
            if len(interface.events):
                event = interface.events.pop(0)
            interface.lock.release()

            if event:
                interface.statechart.dispatch(event)
                event = None
        
    def shutdown(self):
        self.running = False

class TicTacToe(object):
    
    def __init__(self):
        self.ui = UI(self)

        self.events = list()
        self.lock = Lock()

        self.statechart = TicTacToeStatechart(self)
        self.statechart.start()
   
        self.t = StatechartThread(self)
        self.t.start()

        self.ui.kick_off()

    def sendEvent(self, event_id):
        self.lock.acquire()
        self.events.append(Event(event_id)) 
        self.lock.release()

    def shutdown(self):
        print "Exiting ui...."
        self.ui.shutdown()

        print "Shutting statechart...."
        self.t.shutdown()

if __name__ == "__main__":
    TicTacToe()    
