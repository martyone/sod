import click

@click.group()
def cli():
    pass

@click.command()
def status():
    pass

@click.command()
def add():
    pass

@click.command()
def reset():
    pass

@click.command()
def commit():
    pass

@click.command()
def log():
    pass
