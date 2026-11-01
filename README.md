# myrazersup
 Fixing up Razer 15 Advanced RZ09-0409BEA3

This is mostly for myself but there's things in there that might help others.

On getting my mid 2021 Razer 15 Advanced setup in CatchyOS, ran into a few problems.

https://github.com/encomjp/razer-control-revived may resolve some of these for most folks, so start there.

All of this was done with the aid of claude code since the thing I intensely dislike about Linux in general is how much time you have to invest into fixing anything. Claude and other agentic models actually make Linux something more people can use. Win win. 

First was fan control, I had already encountered in Bazzite similar issues where the fan either didn't really spin up or didn't manage to adjust to system load. I wanted to make sure that it was setup specifically for this system and working for me. Hence having claude build it instead of simply debugging the existing razer-control work that other amazing people out there built.

Second, was a wake from sleep loop it kept getting into. After about an hour, it mostly came down to S3 sleep support sucks on intel based laptops and this one is no exception. My recommendation - and what I did - was default it to S2 sleep. Not quite as much power savings, but still using less power than a low watt lightbulb. 

Lastly, on fixing the sleep looping issues, my secondary NVME drive was unmounting. I'm still not sure I entirely understand what it did to fix it but.. drive management in Linux is probably one of my least favorite things and i why I had typically used Bazzite rather than a more flexible distro like Catchy. After figuring out how to mount it, make it executable and r/w, and all that jazz, the fixes here helped keep it mounted when it work from sleep since it's my larger drive where I want to install most of my apps, games, and development work.

Peace be with you and continue to fight the Apple and Microsoft monopolies. 
