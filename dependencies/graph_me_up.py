import subprocess
import os
import re
import datetime
from collections import deque
from graphviz import Digraph
import requests

def run_command(command):
    print(f"\nExecuting: {command}")
    subprocess.run(command, shell=True)

# Parse URLs from .gitmodules file and return a list of submodules.
def get_submodules(repo_name):
    repo_path = f"{repos_dir}/{repo_name}"

    command = f"git -C {repo_path} config --file .gitmodules --get-regexp url"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stderr:
        print(f"Error getting submodules for {repo_name}: {stderr.decode('utf-8').strip()}")
        return []

    output = stdout.decode('utf-8')
    print(f"submodule URLs: {output}")

    # Extract repo names from URLs
    submodules = [url.split('/')[-1].replace('.git', '') for url in output.strip().split("\n") if url]
    print(f"submodules: {submodules}")
    return submodules

def clone_repo_or_switch_branch(repo_name, branch_or_tag):
    repo_path = f"{repos_dir}/{repo_name}"
    if not os.path.exists(repo_path):
        clone_repo(repo_name, branch_or_tag)
    else:
        current_branch = subprocess.getoutput(f"git -C {repo_path} rev-parse --abbrev-ref HEAD")
        if current_branch != branch_or_tag:
            print(f"Switching {repo_name} to {branch_or_tag}")
            run_command(f"git -C {repo_path} checkout {branch_or_tag}")
            run_command(f"git -C {repo_path} pull -q")
        else:
            print(f"{repo_name} is already on {branch_or_tag}. Pulling latest changes.")
            pull_repo(repo_name)

def clone_repo(repo_name, branch_or_tag):
    base_command = f"git clone -q --recurse-submodules git@github.com:matter-labs/{repo_name}.git {repos_dir}/{repo_name}"
    if branch_or_tag:
        base_command += f" -b {branch_or_tag}"
    run_command(base_command)

def pull_repo(repo_name):
    run_command(f"git -C {repos_dir}/{repo_name} pull --recurse-submodules")

def read_cargo_toml(repo_name):
    print(f"Searching for Cargo.toml files in {repo_name}...")
    toml_files = []
    for root, _, files in os.walk(f"{repos_dir}/{repo_name}"):
        for filename in files:
            if filename == "Cargo.toml":
                with open(os.path.join(root, filename), 'r') as f:
                    toml_files.append(f.read())
    return toml_files

def extract_dependencies(toml_content):
    dependencies = []
    toml_content = toml_content.split("[dependencies]", 1)

    if len(toml_content) < 2:
        return dependencies

    toml_content = toml_content[1]
    for line in toml_content.split("\n"):
        if line.strip().startswith("#") or 'github.com/matter-labs' not in line:
            continue

        repo_match = re.search(r'https://github.com/matter-labs/([a-zA-Z0-9_-]+)(.git)?', line)
        if repo_match:
            current_dependency = {'repo': repo_match.group(1)}
        else:
            print(f"Could not find repo in line: {line}")
            continue

        branch_match = re.search(r'branch\s*=\s*"([a-zA-Z0-9._-]+)"', line)
        if branch_match:
            current_dependency['branch'] = branch_match.group(1)

        tag_match = re.search(r'tag\s*=\s*"([a-zA-Z0-9._-]+)"', line)
        if tag_match:
            current_dependency['tag'] = tag_match.group(1)

        rev_match = re.search(r'rev\s*=\s*"([a-zA-Z0-9._-]+)"', line)
        if rev_match:
            current_dependency['rev'] = rev_match.group(1)

        branch_or_tag = current_dependency.get('branch') or current_dependency.get('tag') or current_dependency.get('rev')
        if branch_or_tag:
            dependencies.append(f"{current_dependency['repo']}@{branch_or_tag}")
        else:
            dependencies.append(current_dependency['repo'])

    return dependencies

def bfs_dependency_graph(start_repo, start_branch_or_tag):
    graph = {}
    queue = deque([(start_repo, start_branch_or_tag)])
    explored = set()
    encountered = {f"{start_repo}@{start_branch_or_tag}"}

    while queue:
        current_repo, current_version = queue.popleft()
        current_version = current_version or 'unspecified'
        current = f"{current_repo}@{current_version}"
        if current in explored:
            continue

        clone_repo_or_switch_branch(current_repo, current_version)
        cargo_files = read_cargo_toml(current_repo)

        for cargo_file in cargo_files:
            new_dependencies = extract_dependencies(cargo_file)
            for dep in new_dependencies:
                dep_parts = dep.split("@")
                dep_repo = dep_parts[0]
                dep_version = dep_parts[1] if len(dep_parts) > 1 else 'unspecified'
                dep_full = f"{dep_repo}@{dep_version}"

                # Add dependency to queue if it hasn't been encountered yet.
                if dep_full not in encountered:
                    queue.append((dep_repo, dep_version))
                    encountered.add(dep_full)

                # Add edge to graph if it doesn't already exist.
                if (current, dep_full) not in graph:
                    graph[current] = graph.get(current, {})
                    graph[current][dep_repo] = dep_version

        submodules = get_submodules(current_repo)
        for submodule in submodules:
            submodule_full = f"{submodule}@submodule"
            if submodule_full not in encountered:
                queue.append((submodule, 'submodule'))
                encountered.add(submodule_full)

            if (current, submodule_full) not in graph:
                graph[current] = graph.get(current, {})
                graph[current][submodule] = "submodule"

        explored.add(current)

    return graph

def is_public(repo_name, gh_token):
    headers = {
        "Authorization": f"token {gh_token}"
    } if gh_token else {}

    repo_api_url = f"https://api.github.com/repos/matter-labs/{repo_name}"
    response = requests.get(repo_api_url, headers=headers)

    return response.status_code == 200

def visualize_graph(graph, start_repo, gh_token):
    dot = Digraph(comment='Dependency Graph')
    green_nodes = set()

    # Make all the public repos green.
    for node, children in graph.items():
        repo_name = node.split("@")[0]
        if is_public(repo_name, gh_token):
            green_nodes.add(node)

        for child, version in children.items():
            child_with_version = f"{child}@{version}" if version else child
            if is_public(child, gh_token):
                green_nodes.add(child_with_version)

    # Create all nodes first -- take all parents then add all their children. Then add them to the visualization.
    all_nodes = set(graph.keys())
    for node, children in graph.items():
        for child, version in children.items():
            child_with_version = f"{child}@{version}" if version else child
            all_nodes.add(child_with_version)

    for node in all_nodes:
        if node in green_nodes:
            dot.node(node, color='black', fillcolor='green', style='filled')
        else:
            dot.node(node, color='black')

    # Add edges
    for node, children in graph.items():
        for child, version in children.items():
            # child_with_version = f"{child}@{version}" if version else child
            child_with_version = f"{child}@{version}"
            dot.edge(node, child_with_version)

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dot.render(f'Dependency Graph for {start_repo} {date}', view=True)


# start_repo = "compiler-tester"
start_repo = "zksync-2-dev"
# start_repo = "zksync-era"
start_branch_or_tag = "main"
repos_dir = f'{start_repo}_deps_repos'

GH_TOKEN = " " # TODO "<REPLACE_ME>"

def main():
    if not os.path.exists(repos_dir):
        os.mkdir(repos_dir)
    graph = bfs_dependency_graph(start_repo, start_branch_or_tag)
    visualize_graph(graph, start_repo, GH_TOKEN)

if __name__ == "__main__":
    main()
