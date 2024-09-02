from jira import JIRA
import requests

jira = JIRA(server='http://jira.intchains.in:9000', basic_auth=('xiafeng.luo', 'Luoxiafeng1990@@'))

projects = jira.projects() 
print(projects)

jql = "project = 'RDC: Wangshu SDK'"
issues = jira.search_issues(jql,fields="summary, priority, status, creator, created, customfield_11200", maxResults=-1)
print(issues)