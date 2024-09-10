from flask import Flask, render_template, request
from jira import JIRA
import matplotlib.pyplot as plt
import matplotlib
import io
import base64
from jira.exceptions import JIRAError
import collections

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

# 获取与指定项目相关的 Boards
def get_boards(project_name=None):
    try:
        boards = jira.boards()  # 获取所有 Boards
        board_name = "ALL"
        if project_name:
            # 筛选与指定项目名称相关的 Boards
            relevant_boards = [board for board in boards if board.name.lower() in board_name.lower()]
            return relevant_boards
        else:
            # 如果未指定项目名称，则返回所有 Boards
            return boards
    except JIRAError as e:
        print(f"Error fetching boards: {e}")
        return []

def get_issues_old(jira, jql):
    """Fetch issues based on JQL without retries."""
    try:
        all_issues = []
        start_at = 0
        max_results = 1000  # 每次获取的最大数量
        issues = jira.search_issues(jql, startAt=start_at, maxResults=max_results)
        all_issues.extend(issues)
        return all_issues
    except JIRAError as e:
        print(f"Error fetching issues with JQL {jql}: {e}")
        return []  # 返回空列表或部分结果

def get_issues(jira, jql, cache={}):
    # 检查查询结果是否已经缓存
    if jql in cache:
        print(f"Returning cached results for JQL: {jql}")
        return cache[jql]

    try:
        all_issues = []
        start_at = 0
        max_results = 1000  # 每次获取的最大数量
        
        # 执行远程查询
        issues = jira.search_issues(jql, startAt=start_at, maxResults=max_results)
        all_issues.extend(issues)

        # 将查询结果缓存
        cache[jql] = all_issues
        
        return all_issues
    except JIRAError as e:
        print(f"Error fetching issues with JQL {jql}: {e}")
        return []  # 返回空列表或部分结果

def get_epic_data(project_name):
    try:
        # 获取所有的 Epics
        jql = f"issuetype = Epic AND project = '{project_name}'"
        epics = get_issues(jira, jql)

        # 预先获取所有与该项目相关的 Stories
        all_stories_jql = f'issuetype = Story AND project = "{project_name}"'
        all_stories = get_issues(jira, all_stories_jql)

        epic_data = []
        completed_epics = 0

        for epic in epics:
            issue_key = epic.key
            summary = epic.fields.summary
            status = epic.fields.status.name.lower()  # 统一转换为小写
            target_version = getattr(epic.fields, 'customfield_10007', 'N/A')
            
            # 从已获取的所有 stories 中筛选与当前 epic 相关的 stories
            epic_stories = [story for story in all_stories if getattr(story.fields, 'customfield_10008', None) == issue_key]
            story_count = len(epic_stories)
            completed_stories = sum(1 for story in epic_stories if story.fields.status.name.lower() == 'done')
            completion_percentage = (completed_stories / story_count * 100) if story_count > 0 else 0
            
            if status == 'done':
                completed_epics += 1

            epic_data.append({
                'Issue Key': issue_key,
                'Summary': summary,
                'Status': epic.fields.status.name,
                'Target Version': target_version,
                'Story Count': story_count,
                'Completion Percentage': f"{completion_percentage:.1f}%"
            })

        epic_statistics = {
            'total': len(epics),
            'completed': completed_epics,
            'incomplete': len(epics) - completed_epics
        }

        return epics, epic_data, epic_statistics
    except Exception as e:
        print(f"Error fetching epic data for project {project_name}: {e}")
        return [], [], {'total': 0, 'completed': 0, 'incomplete': 0}

def get_sprint_data(project_name):
    try:
        boards = get_boards(project_name)
        if not boards:
            print(f"No boards found for project {project_name}")
            return []

        # 使用第一个相关的 Board ID
        board_id = boards[0].id
        sprints = jira.sprints(board_id)  # 使用 Board ID 获取所有的 Sprints

        sprint_data = []
        for sprint in sprints:
            sprint_id = sprint.id
            sprint_name = sprint.name
            
            # 获取 Sprint 中的所有 Story
            jql = f"issuetype = Story AND sprint = {sprint_id} AND project = '{project_name}'"
            stories = get_issues(jira, jql)
            total_stories = len(stories)
            completed_stories = sum(1 for story in stories if story.fields.status.name.lower() == 'done')
            completion_percentage = (completed_stories / total_stories * 100) if total_stories > 0 else 0
            
            sprint_data.append({
                'Sprint Name': sprint_name,
                'Total Stories': total_stories,
                'Completed Stories': completed_stories,
                'Moved to Next Sprint': total_stories - completed_stories
            })

        return sprint_data
    except Exception as e:
        print(f"Error fetching sprint data for project {project_name}: {e}")
        return []

def get_delivery_data(epics):
    """
    统计每个 Epic 的 label 及其完成情况。

    Parameters:
    epics : list
        所有的 Epic 问题列表。

    Returns:
    dict
        各 label 对应的统计数据。
    """
    label_data = collections.defaultdict(lambda: {'total': 0, 'completed': 0})

    # 统计每个 Epic 的 label 和对应的完成情况
    for epic in epics:
        labels = getattr(epic.fields, 'labels', [])
        status = epic.fields.status.name.lower()  # 将状态转为小写方便比较

        if labels:
            for label in labels:
                # 统计 Epic 数量
                label_data[label]['total'] += 1
                # 如果 Epic 状态为 'done' 则计入完成的数量
                if status == 'done':
                    label_data[label]['completed'] += 1

    return label_data

def create_delivery_plot(label_data):
    """
    根据 label 数据创建 Delivery 完成情况的柱状图。

    Parameters:
    label_data : dict
        各 label 对应的统计数据。

    Returns:
    str
        图像的 Base64 编码 URL。
    """
    labels = list(label_data.keys())
    total_counts = [data['total'] for data in label_data.values()]
    completed_counts = [data['completed'] for data in label_data.values()]
    completion_percentages = [completed / total * 100 if total > 0 else 0 
                              for completed, total in zip(completed_counts, total_counts)]

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.suptitle('Delivery 完成情况', fontsize=16, fontweight='bold')

    bars = ax.bar(labels, total_counts, color='lightblue', label='Total Epics')
    ax.bar(labels, completed_counts, color='green', label='Completed Epics')

    # 标记每个柱子的完成数量、总数和百分比
    for bar, total, completed, percentage in zip(bars, total_counts, completed_counts, completion_percentages):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height, f'{completed}/{total} ({percentage:.1f}%)', 
                ha='center', va='bottom', fontsize=10, color='black')

    ax.set_xlabel('Labels')
    ax.set_ylabel('Epic Count')
    ax.set_title('Epic Completion by Label')

    # 旋转标签并调整边距
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=10)
    plt.xticks(rotation=45, ha='right')
    fig.tight_layout(pad=3.0)  # 调整布局以避免标签被截断
    ax.legend()

    # 保存图表
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    delivery_plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
    plt.close()

    return delivery_plot_url

def create_story_plot(project_name, all_stories, done_stories, not_done_stories):
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.suptitle('Story 完成情况', fontsize=16, fontweight='bold')

    # 数据和颜色
    categories = ['Completed Stories', 'Incomplete Stories']
    counts = [done_stories, not_done_stories]
    colors = ['green', 'red']

    # 绘制柱状图
    bars = ax.bar(categories, counts, color=colors)

    # 标记每个区域的数量
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height, f'{int(height)}', 
                ha='center', va='bottom', fontsize=10, color='black')

    ax.set_ylabel('Count')
    ax.set_title(f'Story Statistics for {project_name}')

    # 保存图表
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    story_plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
    plt.close()

    return story_plot_url

def create_story_completion_pie_chart(done_stories, not_done_stories):
    """
    创建Story完成情况的饼图，与Epic饼图保持一致的风格。

    Parameters:
    done_stories : int
        已完成的Story数量。
    not_done_stories : int
        未完成的Story数量。

    Returns:
    str
        图像的Base64编码URL。
    """
    story_sizes = [done_stories, not_done_stories]
    story_labels = ['Completed', 'Incomplete']
    explode = (0.1, 0)  # 分离第一个部分
    colors = ['green', 'red']

    fig, ax = plt.subplots(figsize=(7, 5))
    fig.suptitle('Story 完成情况', fontsize=16, fontweight='bold')

    if sum(story_sizes) > 0:
        ax.pie(story_sizes, explode=explode, labels=story_labels, autopct='%1.1f%%', colors=colors, 
               shadow=True, startangle=140)
        ax.set_title('Story Completion Percentage')
    else:
        ax.text(0.5, 0.5, 'No data to display', horizontalalignment='center', 
                verticalalignment='center', transform=ax.transAxes)
        ax.set_title('Story Completion Percentage')

    # 保存图表
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    story_completion_pie_url = base64.b64encode(buf.getvalue()).decode('utf8')
    plt.close()

    return story_completion_pie_url

@app.route('/')
def home():
    return render_template('index.html', projects=projects)

@app.route('/project_stats')
def project_stats():
    project_name = request.args.get('project_name')
    
    if not project_name:
        return "Project name not found", 400

    try:
        # 获取所有与项目相关的 Stories
        jql = f"issuetype = Story AND project = '{project_name}'"
        all_stories_issues = get_issues(jira, jql)

        # 统计完成和未完成的 Stories
        done_stories = sum(1 for issue in all_stories_issues if hasattr(issue.fields, 'status') and issue.fields.status.name.lower() == 'done')
        not_done_stories = len(all_stories_issues) - done_stories
        all_stories = len(all_stories_issues)

        # 获取 Epics 及其统计数据
        epics, epic_data, epic_statistics = get_epic_data(project_name)

        # 获取 Sprint 数据
        sprint_data = get_sprint_data(project_name)

        # 生成 Delivery 完成情况的数据和图表
        label_data = get_delivery_data(epics)
        delivery_plot_url = create_delivery_plot(label_data)

        # 筛选出 Sprint 不为空且状态未完成的 Story
        stories_with_sprints = []
        for story in all_stories_issues:
            if hasattr(story.fields, 'sprint') and story.fields.sprint and hasattr(story.fields, 'status') and story.fields.status.name.lower() != 'done':
                stories_with_sprints.append(story)

        # 创建 Story 完成情况的图表
        story_plot_url = create_story_plot(project_name, all_stories, done_stories, not_done_stories)

        # 创建 Story 完成情况的饼图
        story_completion_pie_url = create_story_completion_pie_chart(done_stories, not_done_stories)

        # 创建 Epic 完成情况的图表
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
        explode = (0.1, 0)
        colors = ['green', 'red']

        if sum(epic_sizes) > 0:
            ax4.pie(epic_sizes, explode=explode, labels=epic_labels, autopct='%1.1f%%', colors=colors, 
                    shadow=True, startangle=140)
            ax4.set_title('Epic Completion Percentage')
        else:
            ax4.text(0.5, 0.5, 'No data to display', horizontalalignment='center', 
                     verticalalignment='center', transform=ax4.transAxes)
            ax4.set_title('Epic Completion Percentage')

        # 保存 Epic 图表
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        epic_plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
        plt.close()

        # 创建 Sprint 完成情况的图表
        fig, ax5 = plt.subplots(figsize=(10, 6))
        fig.suptitle('Sprint 完成情况', fontsize=16, fontweight='bold')

        # 使用 sprint_data 中的 Sprint Name 作为 X 轴，total_stories 作为 Y 轴
        sprint_names = [sprint['Sprint Name'] for sprint in sprint_data]
        total_stories = [sprint['Total Stories'] for sprint in sprint_data]
        completed_stories = [sprint['Completed Stories'] for sprint in sprint_data]

        # 绘制柱状图，只显示总数和已完成数
        bars_total = ax5.bar(sprint_names, total_stories, label='Total Stories', color='lightblue')
        bars_completed = ax5.bar(sprint_names, completed_stories, label='Completed Stories', color='green')

        # 在柱状图上标记 Story 数量和完成百分比
        for bar_total, bar_completed, total, completed in zip(bars_total, bars_completed, total_stories, completed_stories):
            height_total = bar_total.get_height()
            height_completed = bar_completed.get_height()

            ax5.text(bar_total.get_x() + bar_total.get_width() / 2, height_total, f'{total}', 
                    ha='center', va='bottom', fontsize=10, color='black')
            
            if total > 0:
                completion_percentage = (completed / total * 100)
                ax5.text(bar_completed.get_x() + bar_completed.get_width() / 2, height_completed, 
                         f'{completion_percentage:.1f}%', ha='center', va='center', fontsize=10, color='white')

        ax5.set_ylabel('Count')
        ax5.set_title('Sprint Completion Statistics')
        ax5.legend()

        # 保存 Sprint 图表
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        sprint_plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
        plt.close()

        return render_template('project_stats.html', projects=projects, project_name=project_name, 
                               story_plot_url=story_plot_url, epic_plot_url=epic_plot_url, 
                               sprint_plot_url=sprint_plot_url, delivery_plot_url=delivery_plot_url,
                               epic_data=epic_data, sprint_data=sprint_data, 
                               stories_with_sprints=stories_with_sprints,
                               story_completion_pie_url=story_completion_pie_url)
    except JIRAError as e:
        print(f"Error generating project statistics: {e}")
        if "HTTP 502" in str(e):
            return "The JIRA server is currently unavailable (HTTP 502). Please try again later.", 502
        return "An error occurred while generating the project statistics. Please try again later.", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
