import subprocess


def test_hello_command_valid_invocation():
    result = subprocess.run(
        ["uv", "run", "hello"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "Hello, World!\n"
    assert result.stderr == ""
