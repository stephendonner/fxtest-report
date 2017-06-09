from datetime import datetime
import os
import sys

from colour import Color
from humanize import naturaldelta
from jinja2 import Environment, FileSystemLoader

import matplotlib
matplotlib.use('Agg')  # force matplotlib to not use any xwindows backend

import matplotlib.pyplot as plt
import matplotlib.pylab as pylab
import pandas as pd
import requests
import seaborn as sns

params = {
    'legend.fontsize': 'x-small',
    'axes.labelsize': 'x-small',
    'axes.titlesize': 'x-small',
    'xtick.labelsize': 'x-small',
    'ytick.labelsize': 'x-small',
    'legend.edgecolor': 'grey',
    'legend.fancybox': True,
    'legend.facecolor': 'white'}
pylab.rcParams.update(params)
sns.set_style('darkgrid')




def get_data(query):
    url = 'http://activedata.allizom.org/query'
    r = requests.post(url, data=query).json()
    return pd.DataFrame(r['data'], columns=r['header'])


def get_durations():
    return get_data("""{
    "from":"fx-test",
    "groupby":[
        {"name":"job","value":"run.job_name"},
        {"name":"test_id","value":"test.full_name"},
        {"name":"test_name","value":"test.name"}
    ],
    "select":[
        {
            "name":"d90",
            "aggregate":"percentile",
            "percentile":0.9,
            "value":"result.duration"
        },
        {
            "name":"dtotal",
            "aggregate":"sum",
            "value":"result.duration"
        },
        {
            "name":"count",
            "aggregate":"count"
        },
        {
            "name":"failures",
            "aggregate":"sum",
            "value":{"when":{"eq":{"result.ok":"F"}}, "then":1, "else":0}
        },
        {
            "name":"start",
            "aggregate":"min",
            "value":"run.stats.start_time"
        },
        {
            "name":"end",
            "aggregate":"max",
            "value":"run.stats.end_time"
        }
    ],
    "where":{"and":[
        {"eq":{"run.jenkins_url":"https://fx-test-jenkins.stage.mozaws.net/"}},
        {"gt":{"run.stats.start_time":{"date":"today-4week"}}}
    ]},
    "limit":1000
}""")


def get_outcomes():
    return get_data("""{
    "from":"fx-test",
    "edges":[
        {"name":"job","value":"run.job_name","allowNulls":false},
        {
            "name":"date",
            "value":"result.end_time",
            "allowNulls":false,
            "domain":{
                "type":"time",
                "min":"today-12week",
                "max":"today-1day",
                "interval":"day"
            }
        },
        {"name":"result","value":"result.result","allowNulls":false},
        {"name":"ok","value":"result.ok"}
    ],
    "where":{"and":[
        {"eq":{"run.jenkins_url":"https://fx-test-jenkins.stage.mozaws.net/"}}
    ]},
    "limit":1000,
    "format":"table"
}""")


def get_lowest_pass_rate(df):
    return get_lowest_pass_rate_jobs(df)


def get_lowest_pass_rate_jobs(df, limit=10):
    colors = list(Color('red').range_to(Color('lime'), 101))
    jdf = df.groupby(by='job', sort=False).sum()
    jdf['pass'] = 1 - jdf['failures']/jdf['count']  # recalculate pass rate
    jobs = jdf.sort_values('pass', ascending=True) \
        .reset_index()[:limit] \
        .to_dict(orient='records')
    for j in jobs:
        pc = j['pass'] * 100
        j['pass'] = {
            'percent': '{0:.0f}%'.format(pc),
            'color': colors[int(pc)].hex}
        j['tests'] = get_lowest_pass_rate_tests(df, j['job'])
    return jobs


def get_lowest_pass_rate_tests(df, job, limit=10):
    colors = list(Color('red').range_to(Color('lime'), 101))
    tests = df[df['job'] == job] \
        .sort_values('pass', ascending=True)[:limit] \
        .to_dict(orient='records')
    for t in tests:
        pc = t['pass'] * 100
        t['pass'] = {
            'percent': '{0:.0f}%'.format(pc),
            'color': colors[int(pc)].hex}
    return tests


def get_most_failing(df):
    return [{
        'job': j['job'],
        'failures': j['failures'],
        'tests': get_most_failing_tests(df, j['job'])}
            for j in get_most_failing_jobs(df)]


def get_most_failing_jobs(df, limit=10):
    return df.groupby(by='job', sort=False).sum() \
        .sort_values('failures', ascending=False) \
        .reset_index()[:limit] \
        .to_dict(orient='records')


def get_most_failing_tests(df, job, limit=10):
    return df[df['job'] == job] \
        .sort_values('failures', ascending=False)[:limit] \
        .to_dict(orient='records')


def get_slowest(df):
    return [{
        'job': j['job'],
        'duration': j['duration'],
        'tests': get_slowest_tests(df, j['job'])}
            for j in get_slowest_jobs(df)]


def get_slowest_jobs(df, limit=10):
    df = df.groupby(by='job', sort=False).sum() \
        .sort_values('d90', ascending=False) \
        .reset_index()[:limit]
    df['duration'] = df['d90'].apply(lambda x: naturaldelta(x))
    return df.to_dict(orient='records')


def get_slowest_tests(df, job, limit=10):
    df = df[df['job'] == job] \
        .sort_values('d90', ascending=False)[:limit]
    df['duration'] = df['d90'].apply(lambda x: naturaldelta(x))
    return df.to_dict(orient='records')


def get_longest(df):
    return [{
        'job': j['job'],
        'duration': j['duration'],
        'tests': get_longest_tests(df, j['job'])}
            for j in get_longest_jobs(df)]


def get_longest_jobs(df, limit=10):
    df = df.groupby(by='job', sort=False).sum() \
        .sort_values('dtotal', ascending=False) \
        .reset_index()[:limit]
    df['duration'] = df['dtotal'].apply(lambda x: naturaldelta(x))
    return df.to_dict(orient='records')


def get_longest_tests(df, job, limit=10):
    df = df[df['job'] == job] \
        .sort_values('dtotal', ascending=False)[:limit]
    df['duration'] = df['dtotal'].apply(lambda x: naturaldelta(x))
    return df.to_dict(orient='records')


if __name__ == "__main__":
    ddf = get_durations()
    generated = datetime.now()
    start = datetime.fromtimestamp(ddf['start'].min())
    end = datetime.fromtimestamp(ddf['end'].max())
    ddf['failures'] = ddf['failures'].astype(int)
    ddf['pass'] = 1 - ddf['failures']/ddf['count']  # calculate pass rate
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('template.html')
    template_vars = {
        'total': '{:,}'.format(ddf['count'].sum()),
        'start':  start.strftime('%d-%b-%Y'),
        'end': end.strftime('%d-%b-%Y'),
        'generated': {
            'date': generated.strftime('%d-%b-%Y'),
            'time': generated.strftime('%H:%M:%S')},
        'lowest_pass_rate': get_lowest_pass_rate(ddf),
        'most_failing': get_most_failing(ddf),
        'slowest': get_slowest(ddf),
        'longest': get_longest(ddf)}

    o = {'T': 'expected', 'F': 'unexpected'}
    odf = get_outcomes()
    odf['date'] = pd.to_datetime(odf['date'], unit='s')
    jodf = odf.groupby(by=['job', 'date', 'ok', 'result'])['count'] \
        .sum().unstack(level=2).unstack()

    jobs = jodf.index.levels[0]
    fig, axes = plt.subplots(len(jobs) + 1, 2, sharex=True, figsize=(10, 40))
    plt.subplots_adjust(hspace=0.3, wspace=0.2)

    todf = odf.groupby(by=['date', 'ok', 'result'])['count'] \
        .sum().unstack(level=1).unstack()

    for ok, ax in zip(o.keys(), axes[0]):
        a = todf[ok].plot(ax=ax, title='all jobs ({} outcomes)'.format(o[ok]))
        a.legend(loc='upper left', frameon=True).set_title('')

    for job, ax in zip(jobs, axes[1:]):
        for ok, ax in zip(o.keys(), ax):
            t = '{} ({} outcomes)'.format(job, o[ok])
            a = jodf.loc[job][ok].plot(ax=ax, title=t)
            a.legend(loc='upper left', frameon=True).set_title('')
            a.set_ylim(ymin=0)
            a.set_xlabel('')

    path = sys.argv[1]
    fig.savefig(
        os.path.join(os.path.dirname(path), 'overview.png'),
        bbox_inches='tight', pad_inches=0)

    html = template.render(template_vars)
    with open(path, 'w') as f:
        f.writelines(html)
