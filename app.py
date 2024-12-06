from flask import Flask, render_template, jsonify
import boto3
import plotly.graph_objs as go
from datetime import datetime, timedelta
import pandas as pd

app = Flask(__name__)

# AWS клієнти
ec2_client = boto3.client('ec2')
cloudwatch_client = boto3.client('cloudwatch')

# --- Функції для збору даних ---
def get_ec2_instances():
    """Отримати всі EC2 інстанси та їх статус."""
    instances = ec2_client.describe_instances()
    instance_data = []
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            instance_data.append({
                'InstanceId': instance['InstanceId'],
                'State': instance['State']['Name'],
                'Tags': instance.get('Tags', []),
                'Type': instance['InstanceType'],
                'LaunchTime': instance['LaunchTime'].strftime("%Y-%m-%d %H:%M:%S"),
                'PrivateIpAddress': instance.get('PrivateIpAddress'),
                'PublicIpAddress': instance.get('PublicIpAddress')
            })
    return instance_data


def get_instance_metrics(instance_id, metric_name, period=3600, start_time=None):
    """Отримує історичні дані метрик EC2 з CloudWatch."""
    if not start_time:
        start_time = datetime.utcnow() - timedelta(hours=24)

    response = cloudwatch_client.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName=metric_name,
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=start_time,
        EndTime=datetime.utcnow(),
        Period=period,
        Statistics=['Average']
    )

    data_points = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
    timestamps = [dp['Timestamp'] for dp in data_points]
    values = [dp['Average'] for dp in data_points]

    return timestamps, values


def group_instances_by_tag(instances, tag_key):
    """Групує інстанси за заданим тегом."""
    grouped = {}
    for instance in instances:
        tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
        group = tags.get(tag_key, 'Ungrouped')
        if group not in grouped:
            grouped[group] = []
        grouped[group].append(instance)
    return grouped


# --- Маршрути ---
@app.route('/')
def home():
    """Головна сторінка."""
    instances = get_ec2_instances()
    return render_template('home.html', instances=instances)


@app.route('/instance/<instance_id>')
def instance_details(instance_id):
    """Деталі окремого інстанса."""
    metrics = {
        'CPUUtilization': get_instance_metrics(instance_id, 'CPUUtilization'),
        'DiskReadBytes': get_instance_metrics(instance_id, 'DiskReadBytes'),
        'NetworkIn': get_instance_metrics(instance_id, 'NetworkIn')
    }

    graphs = []
    for metric, (timestamps, values) in metrics.items():
        graph = go.Figure(
            data=[go.Scatter(x=timestamps, y=values, mode='lines', name=metric)],
            layout=go.Layout(title=metric, xaxis_title='Time', yaxis_title=metric)
        )
        graphs.append(graph.to_html(full_html=False))

    return render_template('instance_details.html', instance_id=instance_id, graphs=graphs)


@app.route('/groups')
def groups():
    """Сторінка з групами інстансів."""
    instances = get_ec2_instances()
    grouped = group_instances_by_tag(instances, 'Group')
    return render_template('groups.html', groups=grouped)


# --- Шаблони ---
@app.route('/static/<path:path>')
def send_static(path):
    """Обслуговування статичних файлів."""
    return app.send_static_file(path)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=80)

