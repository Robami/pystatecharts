<p align='center'>   </p>
<p align='center'>
<img src='http://lh5.ggpht.com/_YajBMQAFVhU/TIZFP8FH1vI/AAAAAAAAEHI/N1G-HkUd21w/pystatecharts.png' />
</p>
This project provides reusable components to create **statecharts** in Python. Statecharts is a visual formalism for modelling reactive systems. More information about statecharts and their applications can be found [here](http://www.wisdom.weizmann.ac.il/~dharel/SCANNED.PAPERS/Statecharts.pdf).

## Features ##

The following can be easy constructed using the package

  * Simple FSM (Finite State Machine, Mealy as well as Moore models)
  * HSM (Hierarchical State Machine) having shallow history states
  * CSM (Concurrent State Machines containing orthogonal regions)

## Pending ##

The following features are now supported.
  * counting guards
  * sending data with events
  * sending yaml data
  * zeromq (rabbitmq hooks are present but not tested)
  * remote procedure calls
  * turning INI design files into statecharts

The following features are currently unsupported by the package but are aimed for
in the future releases

  * A GUI for designing statecharts graphically, generating an INI design file as output



## Example ##

Please refer to the [example](https://code.google.com/p/pystatecharts/wiki/Example) page to understand how to use the pystatechart library.