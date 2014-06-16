# SolutionNet (spacechem.net)

This is the source code for [SolutionNet](http://spacechem.net), a site for sharing and comparing solutions for the game [SpaceChem](http://www.spacechemthegame.com).

## Disclaimers/Warnings

I have not actively maintained SolutionNet in years. I am willing to merge in pull requests with fixes/enhancements if they are implemented in a reasonable way and have been tested.

All image files in the `static/` directory except the SolutionNet logo were extracted from the game's assets and are the property of [Zachtronics Industries](http://www.zachtronics.com/).

SolutionNet was one of my first projects using multiple technologies, including Python, Flask, and SQLAlchemy. There are many things in it that I would do differently now that I have more experience, so I apologize for the messiness/ugliness/etc.

## Getting a dev instance running

The most basic need will be to remove the `.example` extension from the `spacechem.cfg.example` and `spacechem.wsgi.example`, and edit them to contain appropriate values for your environment. See [the Flask documentation](http://flask.pocoo.org/docs/) for information about how to set it up, if necessary.

SolutionNet itself uses a PostgreSQL database, but it should be possible to use MySQL, SQLite, or other databases supported by SQLAlchemy as well. An Amazon Web Services account is not necessary unless you want to send the registration emails using SES.

Versions of relevant packages being used on SolutionNet (other versions may not work without requiring modifications):

* boto - 2.0b4
* Flask - 0.6.1
* Flask-SQLAlchemy - 0.11
* Flask-Uploads - 0.1.2
* Flask-WTF - 0.5.2
* py-bcrypt - 0.2
* SQLAlchemy - 0.6.6
* WTForms - 0.6.3
