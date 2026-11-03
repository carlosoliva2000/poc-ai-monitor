<!-- Textos del modo de memoria `per_run` del monitor (una sola conversación durante toda la
     simulación). El código elige la sección y sustituye los marcadores <<...>>. Lo que va antes de
     la primera sección no se usa. -->

## next_turn
This conversation continues. Everything above this message belongs to warnings you have **already answered**: it is only memory of what you saw and decided. The state below is the current one and replaces whatever you remember. Old tool results may be out of date and the data you read earlier is **not valid evidence**: to cite an event id or to fill in `checks` you must call the data tools again in this turn. Respond only to the warning(s) below.

## compacted_objective
[<<t>>] Warning(s) already answered: <<warnings>>. (Details of that turn removed to save space.)

## compacted_result
[Older tool result removed to save space. Call the tool again if you need that data.]

## compacted_turn
- [<<t>>] <<warnings>> -> <<outcome>>

## digest
Earlier warnings, already answered (older details removed to save space):
<<lines>>

## aborted_call
[This call was not executed: the turn ended before it.]
