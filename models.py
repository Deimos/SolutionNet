import bcrypt
import sqlite3

from sqlalchemy import func, and_
from sqlalchemy.orm import backref
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql.expression import desc

from forms import savefiles
from spacechem import db


class User(db.Model):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30))
    email = db.Column(db.String(255))
    password = db.Column(db.String(255))    

    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.set_password(password)

    def set_password(self, password):
        self.password = bcrypt.hashpw(password, bcrypt.gensalt())

    def check_password(self, password):
        return bcrypt.hashpw(password, self.password) == self.password


class Level(db.Model):
    __tablename__ = 'levels'

    level_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    internal_name = db.Column(db.String(255))
    number = db.Column(db.String(5))
    slug = db.Column(db.String(255))
    order1 = db.Column(db.Integer)
    order2 = db.Column(db.Integer)
    category = db.Column(db.String(255))
    outside_view = db.Column(db.Boolean, default=False)


class OfficialScores(db.Model):
    __tablename__ = 'official_scores'

    level_id = db.Column(db.Integer, db.ForeignKey('levels.level_id'), primary_key=True)
    fetch_date = db.Column(db.Date, primary_key=True, default=func.now())
    reactor_counts = db.Column(db.String(255))
    symbol_counts = db.Column(db.String(255))
    cycle_counts = db.Column(db.String(255))

    level = db.relationship('Level', backref='official_scores')


class SaveFile(db.Model):
    __tablename__ = 'savefiles'

    file_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    upload_time = db.Column(db.DateTime, default=func.now())

    user = db.relationship('User', backref='savefiles')

    def __init__(self, user_id):
        self.user_id = user_id

    def process(self, approve_all=True):
        approve_all = bool(approve_all)
        user = User.query.filter_by(user_id=self.user_id).one()
        filename = savefiles.path(user.username+'-'+str(self.file_id)+'.user')
        conn = sqlite3.connect(filename)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        uploaded = 0
        skipped = 0
        recalc_levels = set()

        levels = Level.query.all()
        for level in levels:
            c.execute("SELECT * FROM Level WHERE id = ? AND passed = 1", (level.internal_name,))
            level_row = c.fetchone()
            if level_row:
                # check if a solution with the same statistics already exists
                # if it does, this is (probably?) a duplicate
                try:
                    existing_solution = (Solution.query
                                         .filter(and_(Solution.level_id == level.level_id,
                                                      Solution.user_id == self.user_id,
                                                      Solution.cycle_count == level_row['cycles'],
                                                      Solution.symbol_count == level_row['symbols'],
                                                      Solution.reactor_count == level_row['reactors']))
                                         .one())
                    skipped += 1
                    continue
                except NoResultFound:
                    uploaded += 1
                    recalc_levels.add(level.level_id)

                solution = Solution(self.file_id,
                                    self.user_id,
                                    level.level_id,
                                    level_row['cycles'],
                                    level_row['symbols'],
                                    level_row['reactors'],
                                    approve_all)
                db.session.add(solution)
                db.session.commit()

                c.execute("SELECT * FROM Component WHERE level_id = ?", (level.internal_name,))
                component_rows = c.fetchall()
                for component_row in component_rows:
                    component = Component(solution.solution_id,
                                          component_row['type'],
                                          component_row['x'],
                                          component_row['y'])
                    db.session.add(component)
                    db.session.commit()

                    c.execute("SELECT * FROM Member WHERE component_id = ?", (component_row['rowid'],))
                    member_rows = c.fetchall()
                    for member_row in member_rows:
                        member = Member(component.component_id,
                                        member_row['type'],
                                        member_row['arrow_dir'],
                                        member_row['choice'],
                                        member_row['layer'],
                                        member_row['x'],
                                        member_row['y'],
                                        member_row['element_type'],
                                        member_row['element'])
                        db.session.add(member)

                    c.execute("SELECT * FROM Pipe WHERE component_id = ?", (component_row['rowid'],))
                    pipe_rows = c.fetchall()
                    for pipe_row in pipe_rows:
                        pipe = Pipe(component.component_id,
                                    pipe_row['output_id'],
                                    pipe_row['x'],
                                    pipe_row['y'])
                        db.session.add(pipe)

                    db.session.commit()

        # recalculate the ranks if everything is auto-approved
        if approve_all:
            for level_id in recalc_levels:
                SolutionRank.recalculate(level_id)

        return (uploaded, skipped)


class Leaderboard(db.Model):
    __tablename__ = 'leaderboards'

    leaderboard_id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(255))
    description = db.Column(db.String(255))


class Solution(db.Model):
    __tablename__ = 'solutions'

    solution_id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('savefiles.file_id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    level_id = db.Column(db.Integer, db.ForeignKey('levels.level_id'))
    cycle_count = db.Column(db.Integer)
    symbol_count = db.Column(db.Integer)
    reactor_count = db.Column(db.Integer)
    upload_time = db.Column(db.DateTime, default=func.now())
    description = db.Column(db.String(255))
    youtube = db.Column(db.String(255))
    approved = db.Column(db.Boolean, default=True)

    savefile = db.relationship('SaveFile', backref='solutions')
    user = db.relationship('User', backref='solutions')
    level = db.relationship('Level', backref='solutions')

    def __init__(self, file_id, user_id, level_id, cycle_count, symbol_count, reactor_count, approved=True):
        self.file_id = file_id
        self.user_id = user_id
        self.level_id = level_id
        self.cycle_count = cycle_count
        self.symbol_count = symbol_count
        self.reactor_count = reactor_count
        self.approved = approved


class SolutionRank(db.Model):
    __tablename__ = 'solution_ranks'

    solution_id = db.Column(db.Integer, db.ForeignKey('solutions.solution_id'), primary_key=True)
    leaderboard_id = db.Column(db.Integer, db.ForeignKey('leaderboards.leaderboard_id'), primary_key=True)
    level_id = db.Column(db.Integer, db.ForeignKey('levels.level_id'), primary_key=True)
    reactors = db.Column(db.Integer, primary_key=True, default=0)
    rank = db.Column(db.Integer)

    solution = db.relationship('Solution', backref=db.backref('ranks', cascade='save-update, merge, delete'))
    leaderboard = db.relationship('Leaderboard', backref=db.backref('ranks', cascade='save-update, merge, delete'))
    
    def __init__(self, solution_id, leaderboard_id, level_id, rank, reactors=0):
        self.solution_id = solution_id
        self.leaderboard_id = leaderboard_id
        self.level_id = level_id
        self.rank = rank
        self.reactors = reactors
    
    @property
    def rank_str(self):
        if self.rank % 10 == 1 and self.rank % 100 != 11:
            return str(self.rank) + 'st'
        elif self.rank % 10 == 2 and self.rank % 100 != 12:
            return str(self.rank) + 'nd'
        elif self.rank % 10 == 3 and self.rank % 100 != 13:
            return str(self.rank) + 'rd'
        else:
            return str(self.rank) + 'th'
    
    @staticmethod
    def recalculate(level_id):
        SolutionRank.query.filter(SolutionRank.level_id == level_id).delete()
        
        # cycles
        # first do the "any reactors" leaderboard
        users = set()
        rank = 1

        solutions = (Solution.query
                     .filter(and_(Solution.level_id == level_id,
                                  Solution.approved==True))
                     .order_by('cycle_count',
                               'symbol_count',
                               'reactor_count',
                               'upload_time')
                     .all())
        for solution in solutions:
            if solution.user_id not in users:
                users.add(solution.user_id)
                solution_rank = SolutionRank(solution.solution_id, 1, solution.level_id, rank)
                db.session.add(solution_rank)
                rank += 1

        # then any individual reactor counts if necessary
        if solution.level.outside_view:
            reactor_options = (db.session.query(Solution.reactor_count)
                               .filter(and_(Solution.level_id == level_id,
                                            Solution.reactor_count != 0,
                                            Solution.approved == True))
                               .distinct()
                               .order_by(Solution.reactor_count)
                               .all())
            for reactor_count in reactor_options:
                users = set()
                rank = 1

                solutions = (Solution.query
                             .filter(and_(Solution.level_id == level_id,
                                          Solution.reactor_count == reactor_count[0],
                                          Solution.approved==True))
                             .order_by('cycle_count',
                                       'symbol_count',
                                       'upload_time')
                             .all())
                for solution in solutions:
                    if solution.user_id not in users:
                        users.add(solution.user_id)
                        solution_rank = SolutionRank(solution.solution_id, 1, solution.level_id, rank, reactor_count[0])
                        db.session.add(solution_rank)
                        rank += 1

        # symbols
        # first do the "any reactors" leaderboard
        users = set()
        rank = 1

        solutions = (Solution.query
                     .filter(and_(Solution.level_id == level_id,
                                  Solution.approved==True))
                     .order_by('symbol_count',
                               'cycle_count',
                               'reactor_count',
                               'upload_time')
                     .all())
        for solution in solutions:
            if solution.user_id not in users:
                users.add(solution.user_id)
                solution_rank = SolutionRank(solution.solution_id, 2, solution.level_id, rank)
                db.session.add(solution_rank)
                rank += 1

        # then any individual reactor counts if necessary
        if solution.level.outside_view:
            reactor_options = (db.session.query(Solution.reactor_count)
                               .filter(and_(Solution.level_id == level_id,
                                            Solution.reactor_count != 0))
                               .distinct()
                               .order_by(Solution.reactor_count)
                               .all())
            for reactor_count in reactor_options:
                users = set()
                rank = 1

                solutions = (Solution.query
                             .filter(and_(Solution.level_id == level_id,
                                          Solution.reactor_count == reactor_count[0],
                                          Solution.approved == True))
                             .order_by('symbol_count',
                                       'cycle_count',
                                       'upload_time')
                             .all())
                for solution in solutions:
                    if solution.user_id not in users:
                        users.add(solution.user_id)
                        solution_rank = SolutionRank(solution.solution_id, 2, solution.level_id, rank, reactor_count[0])
                        db.session.add(solution_rank)
                        rank += 1
        db.session.commit()


class Component(db.Model):
    __tablename__ = 'components'

    component_id = db.Column(db.Integer, primary_key=True)
    solution_id = db.Column(db.Integer, db.ForeignKey('solutions.solution_id'))
    type = db.Column(db.String(255))
    x = db.Column(db.Integer)
    y = db.Column(db.Integer)

    solution = db.relationship('Solution', backref=db.backref('components', order_by=(x, y), cascade='save-update, merge, delete'))

    def __init__(self, solution_id, type, x, y):
        self.solution_id = solution_id
        self.type = type
        self.x = x
        self.y = y


class FixedComponent(db.Model):
    __tablename__ = 'components_fixed'

    fixedcomponent_id = db.Column(db.Integer, primary_key=True)
    level_id = db.Column(db.Integer, db.ForeignKey('levels.level_id'))
    type = db.Column(db.String(255))
    x = db.Column(db.Integer)
    y = db.Column(db.Integer)

    level = db.relationship('Level', backref=db.backref('fixedcomponents', order_by=(x, y), cascade='save-update, merge, delete'))


class Pipe(db.Model):
    __tablename__ = 'pipes'

    pipe_id = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.Integer, db.ForeignKey('components.component_id'))
    output_id = db.Column(db.Integer)
    x = db.Column(db.Integer)
    y = db.Column(db.Integer)

    component = db.relationship('Component', backref=db.backref('pipes', cascade='save-update, merge, delete'))

    def __init__(self, component_id, output_id, x, y):
        self.component_id = component_id
        self.output_id = output_id
        self.x = x
        self.y = y


class Member(db.Model):
    __tablename__ = 'members'

    member_id = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.Integer, db.ForeignKey('components.component_id'))
    type = db.Column(db.String(255))
    arrow_dir = db.Column(db.Integer)
    choice = db.Column(db.Integer)
    layer = db.Column(db.Integer)
    x = db.Column(db.Integer)
    y = db.Column(db.Integer)
    element_type = db.Column(db.Integer)
    element = db.Column(db.Integer)

    component = db.relationship('Component', backref=db.backref('members', cascade='save-update, merge, delete'))

    @property
    def color(self):
        if self.layer in (16, 32):
            return "blue"
        elif self.layer in (64, 128):
            return "red"
        else:
            return "feature"

    ARROW_DIRS = {180: "l", -90: "u", 0: "r", 90: "d"}
    ELEMENTS = str.split('XX H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K '
                         'Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr '
                         'Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe '
                         'Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu '
                         'Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra '
                         'Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg '
                         'Bh Hs Mt')

    def __init__(self, component_id, type, arrow_dir, choice, layer, x, y, element_type, element):
        self.component_id = component_id
        self.type = type
        self.arrow_dir = arrow_dir
        self.choice = choice
        self.layer = layer
        self.x = x
        self.y = y
        self.element_type = element_type
        self.element = element
    
    @property
    def image_name(self):
        variant = ""

        if self.type == "feature-bonder":
            return "feature-bonder.png"
        elif self.type == "feature-bonder-minus":
            return "feature-bonder_minus.png"
        elif self.type == "feature-bonder-plus":
            return "feature-bonder_plus.png"
        elif self.type == "feature-fuser":
            return "feature-fuser.png"
        elif self.type == "feature-sensor":
            return "feature-sensor.png"
        elif self.type == "feature-splitter":
            return "feature-splitter.png"
        elif self.type == "feature-tunnel":
            return "feature-tunnel.png"
        elif self.type == "instr-arrow":
            return self.color+"-arrow_"+self.ARROW_DIRS[self.arrow_dir]+".png"
        elif self.type == "instr-bond":
            if self.choice == 0:
                variant = "_plus"
            elif self.choice == 1:
                variant = "_minus"
            return self.color+"-bond"+variant+".png"
        elif self.type == "instr-control":
            if self.choice == 0:
                variant = "a"
            elif self.choice == 1:
                variant = "b"
            elif self.choice == 2:
                variant = "c"
            elif self.choice == 3:
                variant = "d"
            return self.color+"-control_"+variant+"_"+self.ARROW_DIRS[self.arrow_dir]+".png"
        elif self.type == "instr-debug":
            return self.color+"-debug.png"
        elif self.type == "instr-fuse":
            return self.color+"-fuse.png"
        elif self.type == "instr-grab":
            if self.choice == 0:
                variant = "grab_drop"
            elif self.choice == 1:
                variant = "grab"
            elif self.choice == 2:
                variant = "drop"
            return self.color+"-"+variant+".png"
        elif self.type == "instr-input":
            if self.choice == 0:
                variant = "1"
            elif self.choice == 1:
                variant = "2"
            return self.color+"-in_"+variant+".png"
        elif self.type == "instr-output":
            if self.choice == 0:
                variant = "1"
            elif self.choice == 1:
                variant = "2"
            return self.color+"-out_"+variant+".png"
        elif self.type == "instr-rotate":
            if self.choice == 0:
                variant = "cw"
            elif self.choice == 1:
                variant = "ccw"
            return self.color+"-rotate_"+variant+".png"
        elif self.type == "instr-sensor":
            return self.color+"-sensor_"+self.ARROW_DIRS[self.arrow_dir]+".png"
        elif self.type == "instr-split":
            return self.color+"-split.png"
        elif self.type == "instr-start":
            return self.color+"-start_"+self.ARROW_DIRS[self.arrow_dir]+".png"
        elif self.type == "instr-swap":
            return self.color+"-swap.png"
        elif self.type == "instr-sync":
            return self.color+"-sync.png"
        elif self.type == "instr-toggle":
            return self.color+"-toggle_"+self.ARROW_DIRS[self.arrow_dir]+".png"
