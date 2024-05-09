https://github.com/zhayujie/chatgpt-on-wechat/#2%E6%9C%8D%E5%8A%A1%E5%99%A8%E9%83%A8%E7%BD%B2


touch nohup.out                                   # 首次运行需要新建日志文件  
nohup python3 app.py & tail -f nohup.out          # 在后台运行程序并通过日志输出二维码
扫码登录后程序即可运行于服务器后台，此时可通过 ctrl+c 关闭日志，不会影响后台程序的运行。使用 ps -ef | grep app.py | grep -v grep 命令可查看运行于后台的进程，如果想要重新启动程序可以先 kill 掉对应的进程。日志关闭后如果想要再次打开只需输入 tail -f nohup.out。此外，scripts 目录下有一键运行、关闭程序的脚本供使用。