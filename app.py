from flask import Flask, render_template
from jira import JIRA
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

# JIRA 配置
JIRA_SERVER = 'http://jira.intchains.in:9000'
JIRA_AUTH = ('xiafeng.luo', 'Luoxiafeng1990@@')

# 连接到 JIRA
jira = JIRA(server=JIRA_SERVER, basic_auth=JIRA_AUTH)

# 获取所有项目
projects = jira.projects()

# JQL 查询，获取所有属于 'RDC: Wangshu SDK' 项目的 story
jql_all = "issuetype = Story AND project = 'RDC: Wangshu SDK'"

# 一次性获取所有类型的 story
all_stories_issues = jira.search_issues(jql_all, 0, maxResults=1000)

# 统计已完成和未完成的 story 数量
done_stories = sum(1 for issue in all_stories_issues if issue.fields.status.name == 'Done')
not_done_stories = len(all_stories_issues) - done_stories
all_stories = len(all_stories_issues)

@app.route('/')
def home():
    return render_template('index.html', projects=projects)

@app.route('/bsp')
def bsp_page():
    return render_template('bsp.html', projects=projects)

@app.route('/sdp')
def sdp_page():
    return render_template('sdp.html', projects=projects)

@app.route('/all')
def all_page():
    # 创建图表
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))

    # 绘制柱状图
    categories = ['All Stories', 'Completed Stories', 'Incomplete Stories']
    counts = [all_stories, done_stories, not_done_stories]

    bars = ax1.bar(categories, counts, color=['blue', 'green', 'red'])
    ax1.set_ylabel('Count')
    ax1.set_title('Story Statistics')

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

    return render_template('all.html', projects=projects, plot_url=plot_url)

if __name__ == '__main__':
    app.run(debug=True)
