# Introduction #

The CountingGuard is a guard that has been designed with a counter and a threshold.
The CountingGuard will return False until a threshold number of
Events have been received. CountingGuards may be designed to retrigger, that is, after
returning True, if not retrigger\_enabled continue to return True.
If retrigger\_enabled, then return False until the count threshold is again reached.


# Details #

Class CountingGuard(Guard):
> def init(self,threshold,retrigger\_enable)