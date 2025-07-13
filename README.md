# LogLora
Python 3 Life Log of your Lora Radio on Windows
By Jaralowell

# Build in Python v3.13.5

After some time messing with lora, i camme to the opinion that i did not like the web interface mush to monitor my lore node, nor did i want my phone to like be connected to it 24/7 So as a result and some tinkering in Python we came to this litle prodject. Granted i am not a super python coder, to be fair started using it like a year or so ago. So help always welcome to make it even bether!

![Language](https://img.shields.io/badge/language-Python-blue.svg)

What des it do, it collects via the Meshtastic Python Cli the data for recieved data, either via HF or MQTT and shows this in the pannels. Additionally chat in there respectifly so named channels. Also plotted on a map and shows wish one be active.
via Neigborhood packages it can also visualize a path of nodes in the area and stores node information in a local log so even if one be off for some time it will know it previous location and re add it thus on the map if a location package was recieved.

Example
![afbeelding](https://i.gyazo.com/996c6e268b16f6c974b00e3e29d524b7.png)

To Do
* Look in to the Memory usuage over large numbers of hours. Can be up to or higher then 700mb after 24 hours.
* Add more Config options (Currently under test via F2)
