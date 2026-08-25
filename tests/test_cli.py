from scigantic_chembl.cli import main


def test_info_command(capsys):
    exit_code = main(["info"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "chembl_37" in out
    assert "chembl_36" in out


def test_query_command(capsys):
    exit_code = main(["query", "SELECT 1 AS n"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "n" in out
    assert "1" in out
