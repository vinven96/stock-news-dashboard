@echo off
cd /d C:\AIProjects\stock_news_agent_code\
python C:\AIProjects\stock_news_agent_code\stock_news_agent.py
copy C:\AIProjects\stock_news_agent_code\index.html C:\AIProjects\stock_news_agent\
cd /d C:\AIProjects\stock_news_agent
git add .
git diff --cached --quiet || (
    git commit -m "hourly update"
    git push
)