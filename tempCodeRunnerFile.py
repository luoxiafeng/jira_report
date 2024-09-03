from flask import Flask, render_template, request
from jira import JIRA
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import io
import base64
from jira.exceptions import JIRAError

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
try:
    jira = JIRA(server=JIRA_SERVER, basic_auth=JIRA_AUTH)
except Exception as e:
    print(f"Failed to connect to JIRA: {e}")
    jira = None

# 获取所有项目
try:
    projects = jira.projects() if jira else []
except Exception as e:
    print(f"Failed to fetch projects: {e}")
    projects = []

def get_issues(jira, jql):
    """Fetch issues based on JQL without retries."""
    try:
        all_issues = []
        start_at = 0
        max_results = 1000  # 每次获取的最大数量
        issues = jira.search_issues(jql, startAt=start_at, maxResults=max_results)
        all_issues.extend(issues)
        start_at += max_results
        return all_issues
    except JIRAError as e:
        print(f"Error fetching issues with JQL {jql}: {e}")
        return []  # 返回空列表或部分结果

def get_epic_data(project_name):
    try:
        # 获取指定项目的所有 Epic
        jql = f"issuetype = Epic AND project = '{project_name}'"
        epics = get_issues(jira, jql)

        epic_data = []
        completed_epics = 0
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
            if completion_percentage == 100:
                completed_epics += 1

            epic_data.append({
                'Issue Key': issue_key,
                'Summary': summary,
                'Status': status,
                'Target Version': target_version,
                'Story Count': story_count,
                'Completion Percentage': f"{completion_percentage:.1f}%"
            })

        # Epic 完成情况统计
        epic_statistics = {
            'total': len(epics),
            'completed': completed_epics,
            'incomplete': len(epics) - completed_epics
        }

        return epic_data, epic_statistics
    except Exception as e:
        print(f"Error fetching epic data for project {project_name}: {e}")
        return [], {'total': 0, 'completed': 0, 'incomplete': 0}

@app.route('/')
def home():
    return render_template('index.html', projects=projects)

@app.route('/project_stats')
def project_stats():
    project_name = request.args.get('project_name')
    
    if not project_name:
        return "Project name not found", 400

    try:
        # 获取 Story 数据
        jql = f"issuetype = Story AND project = '{project_name}'"
        all_stories_issues = get_issues(jira, jql)

        done_stories = sum(1 for issue in all_stories_issues if issue.fields.status.name == 'Done')
        not_done_stories = len(all_stories_issues) - done_stories
        all_stories = len(all_stories_issues)

        # 获取 Epic 数据
        epic_data, epic_statistics = get_epic_data(project_name)

        # 创建 Story 图表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle('Story 完成情况', fontsize=16, fontweight='bold')

        plt.subplots_adjust(wspace=0.4)

        categories = ['All Stories', 'Completed Stories', 'Incomplete Stories']
        counts = [all_stories, done_stories, not_done_stories]

        bars = ax1.bar(categories, counts, color=['blue', 'green', 'red'])
        ax1.set_ylabel('Count')
        ax1.set_title(f'Story Statistics for {project_name}')

        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2, height, f'{int(height)}', 
                     ha='center', va='bottom', fontsize=10, color='black')

        labels = ['Completed', 'Incomplete']
        sizes = [done_stories, not_done_stories]
        colors = ['green', 'red']
        explode = (0.1, 0)

        ax2.pie(sizes, explode=explode, labels=labels, autopct='%1.1f%%', colors=colors, 
                shadow=True, startangle=140)
        ax2.set_title('Story Completion Percentage')

        # 将 Story 图表保存到字节流
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        story_plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
        plt.close()

        # 创建 Epic 图表
        fig, (ax3, ax4) = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle('Epic 完成情况', fontsize=16, fontweight='bold')

        plt.subplots_adjust(wspace=0.4)

        epic_categories = ['All Epics', 'Completed Epics', 'Incomplete Epics']
        epic_counts = [epic_statistics['total'], epic_statistics['completed'], epic_statistics['incomplete']]

        epic_bars = ax3.bar(epic_categories, epic_counts, color=['blue', 'green', 'red'])
        ax3.set_ylabel('Count')
        ax3.set_title(f'Epic Statistics for {project_name}')

        for bar in epic_bars:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width() / 2, height, f'{int(height)}', 
                     ha='center', va='bottom', fontsize=10, color='black')

        epic_sizes = [epic_statistics['completed'], epic_statistics['incomplete']]
        epic_labels = ['Completed', 'Incomplete']

        ax4.pie(epic_sizes, explode=explode, labels=epic_labels, autopct='%1.1f%%', colors=colors, 
                shadow=True, startangle=140)
        ax4.set_title('Epic Completion Percentage')

        # 将 Epic 图表保存到字节流
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        epic_plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
        plt.close()

        return render_template('project_stats.html', projects=projects, project_name=project_name, 
                               story_plot_url=story_plot_url, epic_plot_url=epic_plot_url, epic_data=epic_data)
    except JIRAError as e:
        print(f"Error generating project statistics: {e}")
        if "HTTP 502" in str(e):
            return "The JIRA server is currently unavailable (HTTP 502). Please try again later.", 502
        return "An error occurred while generating the project statistics. Please try again later.", 500

if __name__ == '__main__':
    app.run(debug=True)
