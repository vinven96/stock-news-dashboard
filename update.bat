@echo off
cd /d C:\AIProjects\stock_news_agent
python stock_news_agent.py
git add .
git diff --cached --quiet || (
    git commit -m "hourly update"
    git push
)