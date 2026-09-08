import json
from refusalscope.model import Trace
from refusalscope.classifier import classify
pairs=[('What is two plus two?','Two plus two is four.'),('Please summarize this paragraph.',"I cannot assist with that request.")]
for prompt,response in pairs:
 v=classify(Trace(prompt=prompt,response=response))
 print(json.dumps({'prompt':prompt,'response':response,'label':v.label.value,'signals':len(v.fired_signals)}))
