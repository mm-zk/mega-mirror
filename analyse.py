import subprocess
import os
import difflib
from termcolor import colored
from tabulate import tabulate

REPOSITORIES = ["zkevm_opcode_defs", "zk_evm", "sync_vm", "zkEVM-assembly", "zkevm_test_harness", "circuit_testing", "heavy-ops-service", "zkevm_tester"]

VERSIONS = ["v1.3.1", "v1.3.2", "v1.3.3", "v1.4.0", "main"]

SKIPPED_COMBINATIONS = [
    ("circuit_testing", "v1.3.1"),
    ("circuit_testing", "v1.3.2"),
    ("circuit_testing", "v1.3.3"),
    ("circuit_testing", "v1.4.0"),
    ("zk_evm", "main"),
    ("sync_vm", "main"),
    ("zkEVM-assembly", "main"),
    ("zkevm_tester", "main"),
]

def clone_repo(name):
    print(f"Refreshing repo {name}")
    if not os.path.exists(name):
        subprocess.run(["git", "clone", f"git@github.com:matter-labs/{name}.git"])
    else:
        subprocess.run(["git", "pull"], cwd=name)



def clone_both_repos(name):
    clone_repo(name)
    clone_repo("era-" + name)


def should_ignore(path):
    # Function to determine if a file or directory should be ignored
    return (".git" in path) or ("target" in path)

def should_ignore_file(file_name):
    return file_name in ['Cargo.toml', 'README.md', 'eraLogo.svg', '.gitignore', 'eraLogo.png', 'Cargo.lock']

def compare_and_print_files(dir1, dir2, show_details=False):
    files_differ = 0
    for root, dirs, files in os.walk(dir1):
        # Remove directories that should be ignored
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d))]
        
        for file in files:
            if should_ignore_file(file):
                continue
            file_path1 = os.path.join(root, file)
            file_path2 = os.path.join(dir2, os.path.relpath(file_path1, dir1))

            if os.path.exists(file_path2):
                # Compare file contents
                with open(file_path1, 'r', encoding='utf-8') as f1, open(file_path2, 'r', encoding='utf-8') as f2:
                    lines1 = f1.readlines()
                    lines2 = f2.readlines()
                
                # Perform a line-by-line comparison
                differ = difflib.Differ()
                diff = list(differ.compare(lines1, lines2))
                
                # Check if files differ
                if any(line.startswith(('+', '-')) for line in diff):
                    print(colored(f"File '{file_path1}' differs:", 'red'))
                    files_differ += 1
                    if show_details:                        
                        # Print the first 2 differing lines
                        max_lines = 6
                        for line in diff:
                            if line.startswith('+'):
                                print(colored(line, 'green'))
                                max_lines -= 1
                            elif line.startswith('-'):
                                print(colored(line, 'red'))
                                max_lines -= 1
                            if max_lines <= 0:
                                break
                        print(f"Total differing lines: {sum(1 for line in diff if line.startswith(('+', '-')))}\n")
                else:
                    pass
            else:
                print(colored(f"File '{file}' is missing in '{dir2}'", 'red'))
      # Check for files in dir2 that are not in dir1
    for root, dirs, files in os.walk(dir2):
        # Remove directories that should be ignored
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d))]
        
        for file in files:
            if should_ignore_file(file):
                continue
            file_path2 = os.path.join(root, file)
            file_path1 = os.path.join(dir1, os.path.relpath(file_path2, dir2))

            if not os.path.exists(file_path1):
                print(colored(f"File '{file}' is in '{dir2}' but not in '{dir1}'", 'red'))
                files_differ += 1

    return files_differ



def diff_branch(repo_name, branch):
    if (repo_name, branch) in SKIPPED_COMBINATIONS:
        return colored("skip", 'grey')
        

    print(f"\n\n====== Comparing repo {repo_name} at branch {branch} =======\n\n")
    era_name = "era-" + repo_name
    p = subprocess.run(["git", "checkout", branch], cwd=repo_name)
    if p.returncode != 0:
        return colored("private checkout failed", "yellow")
    p = subprocess.run(["git", "checkout", branch], cwd=era_name)
    if p.returncode != 0:
        return colored("public checkout failed", "yellow")
    file_differ = compare_and_print_files(repo_name, era_name)
    if file_differ == 0:
        return colored("OK", "green")
    else:
        return colored("File diffs: %d"% file_differ, "red")

    





header = ["Repository"]
for version in VERSIONS:
    header.append(version)

summary = [header]

for repo in REPOSITORIES:
    clone_both_repos(repo)
    repo_summary = [repo]
    for version in VERSIONS:
        files_differ = diff_branch(repo, version)
        
        repo_summary.append(files_differ)
    summary.append(repo_summary)


table = tabulate(summary, headers="firstrow", tablefmt="fancy_grid")

print(table)
        

