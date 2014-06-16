import os
from sqlite3 import DatabaseError
import zipfile

from boto.exception import BotoServerError
from flask import Flask, render_template, abort, request, redirect, session, url_for, flash
from flaskext.sqlalchemy import SQLAlchemy
from flaskext.uploads import configure_uploads, patch_request_class
from sqlalchemy import func, cast, Integer
from sqlalchemy.orm.exc import NoResultFound


app = Flask(__name__)
app.config.from_pyfile('spacechem.cfg')
app.jinja_env.add_extension('jinja2.ext.do')
db = SQLAlchemy(app)


from models import *
from functions import *
from forms import *


configure_uploads(app, savefiles)
patch_request_class(app)


# main page
@app.route('/')
def main_page():
    return render_template('index.html')


@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.route('/register', methods=['GET','POST'])
def register():
    if 'username' in session:
        return redirect(url_for('main_page'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(form.username.data, form.email.data, form.password.data)
        db.session.add(user)
        db.session.commit()

        # send email through SES
        subject = 'Account created for SpaceChem SolutionNet'
        body = ("Thanks for registering on SpaceChem SolutionNet (http://spacechem.net)\n\n"
                "Your username is: {0}").format(user.username)

        try:
            ses_email(app.config, user.email, subject, body)
        except BotoServerError:
            flash('Sending welcome email failed.', 'error')

        session['user_id'] = user.user_id
        session['username'] = user.username

        flash('Registration successful, welcome to SolutionNet!')
        return redirect(url_for('main_page'))

    return render_template('register.html', form=form)


@app.route('/login', methods=['GET','POST'])
def login():
    if 'username' in session:
        return redirect(url_for('main_page'))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter_by(username=form.username.data).one()
            if not user.check_password(form.password.data):
                raise NoResultFound
        except NoResultFound:
            flash('Incorrect login info', 'error')
            return redirect(url_for('login'))

        if form.remember.data:
            session.permanent = True
        session['user_id'] = user.user_id
        session['username'] = user.username
        return redirect('/user/'+user.username)

    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.permanent = False
    return redirect(url_for('main_page'))


@app.route('/user-settings', methods=['GET', 'POST'])
def user_settings():
    if 'username' not in session:
        return redirect(url_for('main_page'))

    user = User.query.filter_by(user_id=session['user_id']).one()

    form = UserSettingsForm(obj=user)
    if form.validate_on_submit():
        try:
            if not user.check_password(form.password.data):
                raise NoResultFound
        except NoResultFound:
            flash('Incorrect current password', 'error')
            return redirect(url_for('user_settings'))
    
        user.email = form.email.data
        if len(form.new_password.data) > 0:
            user.set_password(form.new_password.data)
        db.session.add(user)
        db.session.commit()
    
        flash('User settings updated')
        return redirect(url_for('user_settings'))
    
    return render_template('user_settings.html', form=form, user=user)


@app.route('/upload', methods=['GET','POST'])
def upload():
    if 'username' not in session:
        return redirect(url_for('main_page'))

    num_unapproved = (Solution.query
                      .filter(and_(Solution.user_id == session['user_id'],
                                   Solution.approved == False))
                      .count())
    if num_unapproved > 0:
        flash("You still have unapproved solutions from your last upload, "
              "please decide which of these to keep first before uploading "
              "another save.")
        return redirect('/unapproved')

    form = UploadForm()
    if form.validate_on_submit():
        savefile = SaveFile(session['user_id'])
        db.session.add(savefile)
        db.session.commit()
        filename = savefiles.save(request.files['save'],
                                  name=session['username']+'-'+str(savefile.file_id)+'.')
        try:
            if filename.endswith('.zip'):
                if not zipfile.is_zipfile(savefiles.path(filename)):
                    raise zipfile.BadZipfile
                zipped = zipfile.ZipFile(savefiles.path(filename), 'r')
                zipped_files = zipped.infolist()
                if len(zipped_files) != 1:
                    raise zipfile.BadZipfile
                if not zipped_files[0].filename.endswith('.user'):
                    raise zipfile.BadZipfile
                
                unzipped = open(savefiles.path(filename.replace('.zip', '.user')), 'w')
                unzipped.writelines(zipped.open(zipped_files[0], 'r').readlines())
                unzipped.close()
                
            results = savefile.process(form.upload_all.data)
        except zipfile.BadZipfile:
            flash('Invalid zipped SpaceChem save file. Please ensure that you '
                  'are uploading the correct file, and that it is a zip file '
                  'containing only a single save file.', 'error')
            db.session.delete(savefile)
            db.session.commit()
            os.remove(savefiles.path(filename))
            return redirect('/upload')
        except DatabaseError:
            flash('Invalid SpaceChem save file. Please ensure that you are '
                  'uploading the correct file.', 'error')
            db.session.delete(savefile)
            db.session.commit()
            if filename.endswith('.zip'):
                os.remove(savefiles.path(filename.replace('.zip', '.user')))
            os.remove(savefiles.path(filename))
            return redirect('/upload')

        if (form.upload_all.data):
            flash("Uploaded {0} solutions, skipped {1} previously-uploaded.".format(results[0], results[1]))
            return redirect('/user/'+session['username'])
        else:
            flash("Found {0} potential solutions to upload, skipped {1} previously-uploaded.".format(results[0], results[1]))
            if results[0] == 0:
                return redirect('/user/'+session['username'])
            else:
                return redirect('/unapproved')
    return render_template("upload.html", form=form)


@app.route('/unapproved', methods=['GET', 'POST'])
def unapproved():
    solutions = (Solution.query
                 .filter(and_(Solution.user_id == session['user_id'],
                              Solution.approved == False))
                 .join(Level)
                 .order_by('levels.category', 'order1', 'order2')
                 .all())

    if request.method == 'POST':
        updated = 0
        deleted = 0
        if request.form:
            solution_ids = [int(id) for id in request.form.keys()]
            query = (Solution.query
                     .filter(and_(Solution.user_id == session['user_id'],
                                  Solution.solution_id.in_(solution_ids))))
            updated = query.update({'approved': True}, synchronize_session=False)
            db.session.commit()
            approved = query.all()
            for solution in approved:
                SolutionRank.recalculate(solution.level_id)

        to_delete = (Solution.query
                     .filter(and_(Solution.user_id == session['user_id'],
                                  Solution.approved==False))
                     .all())
        for delete in to_delete:
            db.session.delete(delete)
            deleted += 1
        db.session.commit()
        flash("Uploaded {0} solutions, omitted {1} unwanted solutions.".format(updated, deleted))
        return redirect('/user/'+session['username'])
    else:
        return render_template('unapproved.html', solutions=solutions)


@app.route('/solution/<slug>/<solution_id>', methods=['GET', 'POST'])
def display_solution(slug, solution_id):
    try:
        solution = Solution.query.filter_by(solution_id=solution_id).one()

        # prevent viewing non-approved solutions by anyone except owner
        if not solution.approved and session['user_id'] != solution.user_id:
            raise NoResultFound

        # stop people from making misleading URLs
        if solution.level.slug != slug:
            raise NoResultFound
    except NoResultFound:
        abort(404)

    form = SolutionForm(obj=solution)
    if form.validate_on_submit() and session['user_id'] == solution.user_id:
        solution.description = form.description.data
        solution.youtube = form.youtube.data
        if solution.youtube and not solution.youtube.startswith('http://'):
            solution.youtube = 'http://'+solution.youtube
        db.session.add(solution)
        db.session.commit()

        flash('Solution details updated')
        return redirect('/solution/'+slug+'/'+solution_id)

    reactors = process_solution(solution)

    overview = process_overview(solution)

    return render_template('solution.html',
                           num_reactors=len(reactors),
                           reactors=reactors,
                           overview=overview,
                           solution=solution,
                           ELEMENTS=Member.ELEMENTS,
                           form=form)


@app.route('/solution-delete/<solution_id>')
def delete_solution(solution_id):
    try:
        solution = (Solution.query
                    .filter(and_(Solution.solution_id == solution_id,
                                 Solution.user_id == session['user_id']))
                    .one())
    except NoResultFound:
        abort(404)

    if not request.args or not request.args['confirm']:
        return render_template('solution_delete.html', solution=solution)
    else:
        level_id = solution.level_id
        db.session.delete(solution)
        db.session.commit()
        SolutionRank.recalculate(level_id)

        flash('Solution deleted')
        return redirect('/user/'+session['username'])


@app.route('/user/<username>')
def user_page(username):
    try:
        user = User.query.filter_by(username=username).one()
    except NoResultFound:
        abort(404)

    main_solutions = (Solution.query
                      .filter(and_(Level.category == 'main',
                                   Solution.user_id == user.user_id,
                                   Solution.approved == True))
                      .join(Solution.level)
                      .order_by('levels.order1', 'levels.order2')
                      .all())
    researchnet_solutions = (Solution.query
                             .filter(and_(Level.category == 'researchnet',
                                          Solution.user_id == user.user_id,
                                          Solution.approved == True))
                             .join(Solution.level)
                             .order_by('levels.order1', 'levels.order2')
                             .all())
    tf2_solutions = (Solution.query
                     .filter(and_(Level.category == 'tf2',
                                  Solution.user_id == user.user_id,
                                  Solution.approved == True))
                     .join(Solution.level)
                     .order_by('levels.order1', 'levels.order2')
                     .all())
    corvi_solutions = (Solution.query
                       .filter(and_(Level.category == '63corvi',
                                    Solution.user_id == user.user_id,
                                    Solution.approved == True))
                       .join(Solution.level)
                       .order_by('levels.order1', 'levels.order2')
                       .all())

    return render_template('user.html', **locals())


@app.route('/solution-stats')
def solution_stats_list():
    main_levels = (Level.query
                   .filter_by(category='main')
                   .order_by('order1', 'order2')
                   .all())
    published_levels = (Level.query
                        .filter_by(category='researchnet')
                        .order_by('order1', 'order2')
                        .all())
    tf2_levels = (Level.query
                  .filter_by(category='tf2')
                  .order_by('order1', 'order2')
                  .all())
    corvi_levels = (Level.query
                    .filter_by(category='63corvi')
                    .order_by('order1', 'order2')
                    .all())

    return render_template('solution_stats_list.html', **locals())


@app.route('/solution-stats/<slug>')
def solution_stats(slug):
    try:
        level = Level.query.filter_by(slug=slug).one() 
        scores = (OfficialScores.query
                  .filter_by(level_id=level.level_id)
                  .order_by(desc('fetch_date'))
                  .limit(1)
                  .one())
    except NoResultFound:
        abort(404)
    
    chart_data = dict()

    # convert all the data to ints, after converting to floats first
    cycles_split = map(int, map(float, scores.cycle_counts.split()))
    reactors_split = map(int, map(float, scores.reactor_counts.split()))
    symbols_split = map(int, map(float, scores.symbol_counts.split()))

    # use reactor sum for total because the other ones can have solutions "off the chart" that aren't counted
    chart_data['total_solutions'] = sum(reactors_split[6:])
    
    process_chart_data(reactors_split, chart_data, 'reactor')
    process_chart_data(cycles_split, chart_data, 'cycle')
    process_chart_data(symbols_split, chart_data, 'symbol')
    
    try:
        best_by_cycles = (SolutionRank.query
                          .filter(and_(SolutionRank.leaderboard_id == 1,
                                       SolutionRank.level_id == level.level_id,
                                       SolutionRank.reactors == 0,
                                       SolutionRank.rank == 1))
                          .one())
    except NoResultFound:
        best_by_cycles = None

    try:
        best_by_symbols = (SolutionRank.query
                           .filter(and_(SolutionRank.leaderboard_id == 2,
                                        SolutionRank.level_id == level.level_id,
                                        SolutionRank.reactors == 0,
                                        SolutionRank.rank == 1))
                           .one())
    except NoResultFound:
        best_by_symbols = None

    return render_template('solution_stats.html', 
                           level=level,
                           chart_data=chart_data,
                           best_by_cycles=best_by_cycles,
                           best_by_symbols=best_by_symbols)


@app.route('/leaderboards')
def leaderboards_list():
    main_levels = Level.query.filter_by(category='main').order_by('order1','order2').all()
    published_levels = Level.query.filter_by(category='researchnet').order_by('order1','order2').all()
    tf2_levels = Level.query.filter_by(category='tf2').order_by('order1','order2').all()
    corvi_levels = Level.query.filter_by(category='63corvi').order_by('order1','order2').all()

    return render_template('leaderboard_list.html', **locals())


@app.route('/leaderboards/<level_slug>/<leaderboard_slug>', defaults={'reactors': 0})
@app.route('/leaderboards/<level_slug>/<leaderboard_slug>/1-reactor', defaults={'reactors': 1})
@app.route('/leaderboards/<level_slug>/<leaderboard_slug>/<reactors>-reactors')
def leaderboard(level_slug, leaderboard_slug, reactors):
    try:
        level = Level.query.filter_by(slug=level_slug).one()
        leaderboard = Leaderboard.query.filter_by(slug=leaderboard_slug).one()
    except NoResultFound:
        abort(404)

    solution_ranks = (SolutionRank.query
                      .filter(and_(SolutionRank.leaderboard_id == leaderboard.leaderboard_id,
                                   SolutionRank.level_id == level.level_id,
                                   SolutionRank.reactors == reactors))
                      .order_by('rank')
                      .all())

    reactor_options = (db.session.query(Solution.reactor_count)
                       .filter(and_(Solution.level_id == level.level_id,
                                    Solution.reactor_count != reactors))
                       .distinct()
                       .order_by(Solution.reactor_count)
                       .all())

    return render_template('leaderboard.html', type=leaderboard.slug, **locals())


@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.debug = True
    app.run()
