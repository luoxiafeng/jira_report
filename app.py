from flask import Flask, render_template, request
from jira import JIRA
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import io
import base64

# 禁用 Matplotlib 的 GUI 后端
matplotlib.use('Agg')

# 配置 Matplotlib 使用中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用 SimHei 字体支持中文
plt.rcParams['axes.unicode_minus'] = False   # 正常显示负号

app = Flask(__name__)

# JIRA 配置
JIRA_SERVER = 'http://jira.intchains.in:9000'
JIRA_AUTH = ('xiafeng.luo', 'Luoxiafeng1990@@')

# 连接到 JIRA
jira = JIRA(server=JIRA_SERVER, basic_auth=JIRA_AUTH)

# 获取所有项目
projects = jira.projects()

def get_issues(jira, jql):
    try:
        all_issues = []
        all_issues = jira.search_issues(jql, startAt=0, maxResults=1000)
        return all_issues
    except Exception as e:
        print(f"Failed to get issues: {e}")
        return []

def get_epic_data(project_name):
    try:
        # 获取指定项目的所有 Epic
        jql = f"issuetype = Epic AND project = '{project_name}'"
        epics = get_issues(jira, jql)

        epic_data = []
        for epic in epics:
            issue_key = epic.key
            summary = epic.fields.summary
            status = epic.fields.status.name
            target_version = getattr(epic.fields, 'customfield_10007', 'N/A')  # 假设 target version 是自定义字段
            # 获取该 Epic 下的 Story
            stories_jql = f'"Epic Link" = {issue_key}'
            stories = get_issues(jira, stories_jql)
            story_count = len(stories)
            completed_stories = sum(1 for story in stories if story.fields.status.name == 'Done')
            completion_percentage = (completed_stories / story_count * 100) if story_count > 0 else 0

            epic_data.append({
                'Issue Key': issue_key,
                'Summary': summary,
                'Status': status,
                'Target Version': target_version,
                'Story Count': story_count,
                'Completion Percentage': f"{completion_percentage:.1f}%"
            })
        return epic_data
    except Exception as e:
        print(f"Failed to get epic data: {e}")
        return []

@app.route('/')
def home():
    return render_template('index.html', projects=projects)

@app.route('/project_stats')
def project_stats():
    # 获取项目名称
    project_name = request.args.get('project_name')
    try:
        if not project_name:
            return "Project name not found", 400

        # 生成项目相关的 JQL 查询
        jql = f"issuetype = Story AND project = '{project_name}'"
        
        # 一次性获取所有类型的 story
        all_stories_issues = get_issues(jira, jql)

        # 统计已完成和未完成的 story 数量
        done_stories = sum(1 for issue in all_stories_issues if issue.fields.status.name == 'Done')
        not_done_stories = len(all_stories_issues) - done_stories
        all_stories = len(all_stories_issues)
    except Exception as e:
        f"Failed to get story data: {e}", 500
        pass

    # 获取 Epic 数据
    epic_data = get_epic_data(project_name)
    try:
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))  # 增加宽度以拉大图表间距

        # 调整子图之间的间距
        plt.subplots_adjust(wspace=0.4)  # 调整子图之间的水平间距

        # 绘制柱状图
        categories = ['All Stories', 'Completed Stories', 'Incomplete Stories']
        counts = [all_stories, done_stories, not_done_stories]

        bars = ax1.bar(categories, counts, color=['blue', 'green', 'red'])
        ax1.set_ylabel('Count')
        ax1.set_title(f'Story Statistics for {project_name}')
        # 在柱状图上方标注数量
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2, height, f'{int(height)}', 
                    ha='center', va='bottom', fontsize=10, color='black')

        # 绘制饼图
        labels = ['Completed', 'Incomplete']
        sizes = [done_stories, not_done_stories]
        colors = ['green', 'red']
        explode = (0.1, 0)  # 突出显示已完成的部分

        ax2.pie(sizes, explode=explode, labels=labels, autopct='%1.1f%%', colors=colors, 
                shadow=True, startangle=140)
        ax2.set_title('Story Completion Percentage')

        # 将图表保存到字节流
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
        plt.close()

        return render_template('project_stats.html', projects=projects, plot_url=plot_url, project_name=project_name, epic_data=epic_data)
    except Exception as e:
        return "Failed to generate plot", 500
if __name__ == '__main__':
    app.run(debug=True)
