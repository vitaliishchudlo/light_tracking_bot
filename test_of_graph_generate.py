import matplotlib.pyplot as plt
import numpy as np
import requests

from src.constants import GROUPS_NUMBERS, HEX_RED, HEX_GREEN, HEX_YELLOW, URL_TO_GET_GRAPH_BY_QUEUE


# Function to fetch data for a specific queue
def fetch_data(queue_number):
    headers = {'Content-Type': 'application/json'}
    payload = {'queue': queue_number}
    response = requests.post(URL_TO_GET_GRAPH_BY_QUEUE, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


# Fucntion to plot a graph
def plot_graph(data, queue_number):
    hours_data = data["graphs"]["today"]["hoursList"]

    # Initialize variables for the graph
    hours = [f"{int(item['hour']) - 1}-{int(item['hour'])}" for item in hours_data]
    electricity = [item['electricity'] for item in hours_data]

    # Setting colors: green for 1 (electricity is present), red for 0 (electricity is absent), yellow for 2 (maybe yes, maybe no)
    colors = [HEX_RED if status == 1 else HEX_GREEN if status == 0 else HEX_YELLOW for status in electricity]

    # Set sizes for each section
    sizes = [1] * 24  # Every section is equal, because there are 24 hours

    # Creating a pie chart with a hole
    fig, ax = plt.subplots(figsize=(10, 10))
    wedges, texts = ax.pie(sizes, colors=colors, startangle=90, counterclock=False,
                           wedgeprops={'width': 0.55, 'edgecolor': 'white'})

    # Adding labels for each hour
    for i, p in enumerate(wedges):
        ang = (p.theta2 - p.theta1) / 2. + p.theta1  # Corner for label placement
        x = np.cos(np.deg2rad(ang))
        y = np.sin(np.deg2rad(ang))
        ax.text(x * 0.88, y * 0.88, hours[i], horizontalalignment='center', verticalalignment='center', fontsize=12,
                fontweight='bold')  # більше центровано

    ax.text(0, 0.10, 'Черга', horizontalalignment='center', verticalalignment='center', fontsize=30)
    ax.text(0, -0.10, f"{data['current']['queue']}.{data['current']['subqueue']}", horizontalalignment='center',
            verticalalignment='center', fontsize=35, fontweight='bold')

    ax.set(aspect="equal")  # Display the graph as a circle

    plt.savefig(f'graphs_images/graph_{data['current']['queue']}.{data['current']['subqueue']}.png')

    # # Show the graph
    # plt.show()


# Main part of the script
for group_number in GROUPS_NUMBERS:
    try:
        data = fetch_data(group_number)
        plot_graph(data, group_number)
    except Exception as e:
        print(f"Помилка при обробці черги {group_number}: {e}")
