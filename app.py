from flask import Flask, render_template, redirect, request, jsonify, send_file,session , make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_restful import Api,Resource ,abort
from datetime import timedelta,datetime
from functools import wraps
from flask_jwt_extended import get_jwt_identity,JWTManager, jwt_required, create_access_token
from celery_worker import make_celery
from celery.result import AsyncResult
from celery.schedules import crontab  
import smtplib
from flask_mail import Mail, Message
import pytz
from weasyprint import HTML
from jinja2 import Template
import pandas as pd
ist = pytz.timezone('Asia/Calcutta')
import time
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///grocery_store.sqlite3"
app.config['SECRET_KEY'] = 'SECRET_KEY'

app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'alexeubank819@gmail.com'
app.config['MAIL_PASSWORD'] = "rvda lmts mjqg zwxx"
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True


mail = Mail(app)

api=Api(app)
db = SQLAlchemy(app)
JWTManager(app)
app.config['JWT_TOKEN_LOCATION'] = ['headers', 'query_string']
app.config.update(
   CELERY_BROKER_URL='redis://localhost:6379/1',
    CELERY_RESULT_BACKEND='redis://localhost:6379/2',
    # broker_connection_retry_on_startup = True
)

celery = make_celery(app)
@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Calls test('hello') every 10 seconds.
    # sender.add_periodic_task(10.0, add_together.s(9, 6), name='add every 10')
    sender.add_periodic_task(
        crontab(day_of_month=1,hour=8, minute=00),
        monthly_report.s(),
    )
    sender.add_periodic_task(
        crontab(hour=11, minute=45),
        daily_remainder.s(),
    )

def role_required(roles):
  
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                userlogged = get_jwt_identity()
                email = userlogged.get('email')

                if not email:
                    return {'msg' : 'Invalid Token'} , 403

                user = Member.query.filter_by(email = email).first()
                print(user)
            
                if not user:
                    return {'msg' : 'User not found.'} , 404

                if not user.role in roles:
                    return {'msg' : 'Unauthorised.'} , 401
                return fn(*args, **kwargs)

            except Exception as e:
                return {'msg' : 'Internal Sui Error'} , 500
        return wrapper
    return decorator

class Member(db.Model):
    __tablename__ = 'member'
    username = db.Column(db.String, unique=False,primary_key=True)
    email = db.Column(db.String, unique=True,primary_key=True)
    password = db.Column(db.String(255))
    active = db.Column(db.Boolean)
    role = db.Column(db.String(255))
    approved = db.Column(db.Boolean, default=True, nullable=False)

class Orders(db.Model):
    __tablename__ = 'orders'
    id =db.Column(db.Integer, unique=True,primary_key=True, autoincrement=True)
    order_date=db.Column(db.DateTime(), nullable=False)
    user_email = db.Column(db.String,db.ForeignKey(Member.email,ondelete='CASCADE'),nullable=False)
    qbought=db.Column(db.Integer,nullable=False)
    price_perunit= db.Column(db.Integer,nullable=False)

    pid_order = db.Column(db.Integer,)
    
class Category(db.Model):
    __tablename__ = 'category'
    cname = db.Column(db.String, unique=True)
    cid = db.Column(db.Integer, unique=True,primary_key=True, autoincrement=True)
    newname = db.Column(db.String, nullable=True)
    request_creation=db.Column(db.Boolean, default=False, nullable=False)
    request_deletion=db.Column(db.Boolean, default=False, nullable=False)
    request_edit=db.Column(db.Boolean, default=False, nullable=False)
    product=db.relationship('Product',backref='product',lazy='dynamic', cascade="all, delete, delete-orphan")

class Product(db.Model):
    __tablename__ = 'product'
    pname = db.Column(db.String, unique=True)
    pid = db.Column(db.Integer, unique=True,primary_key=True, autoincrement=True)
    rateperunit = db.Column(db.Integer,nullable=False)
    unit= db.Column(db.String,nullable=False)
    quantity = db.Column(db.Integer,nullable=False)
    product_deletion_req=db.Column(db.Boolean, default=False, nullable=False)
    mfd_date= db.Column(db.Date)# YYYY-MM-DD
    expiry_date =db.Column(db.Date)
    addedon = db.Column(db.DateTime(), nullable=False)
    catid =db.Column(db.Integer,db.ForeignKey(Category.cid,ondelete='CASCADE'),nullable=False)
    cart=db.relationship('Cart',backref='cart',lazy='dynamic', cascade="all, delete, delete-orphan")

class Cart(db.Model):
    __tablename__ = 'cart'
    id =db.Column(db.Integer, unique=True,primary_key=True, autoincrement=True)
    prodid =db.Column(db.Integer,db.ForeignKey(Product.pid,ondelete='CASCADE'),nullable=False)
    qbought=db.Column(db.Integer,nullable=False)
    totalamount=db.Column(db.Integer,nullable=False)
    user_email = db.Column(db.String,db.ForeignKey(Member.email,ondelete='CASCADE'),nullable=False)
    
class CategoryResource(Resource):
    @jwt_required()
    def get(self):
        category = Category.query.all()
        data= []
        for category in category :
            data.append({
                'cid' : category.cid ,
                'cname' : category.cname ,
                'request_creation' : category.request_creation,
                'request_deletion' : category.request_deletion,
                'request_edit' : category.request_edit,
                'newname' : category.newname,

             
            })
      
    
        return data 
    
    # ADMIN ROLE REQUIRED
    
    @jwt_required()
    @role_required(['ADMIN'])
    def post(self):
        data = request.get_json()
        category =  Category(cname=data.get("category"),cid=data.get("cid"),newname="Null",request_creation=False,request_deletion=False,request_edit=False)
        db.session.add(category)
        db.session.commit()
        return jsonify(" CATADDED")
    
    # ADMIN ROLE REQUIRED
    
    @jwt_required()
    @role_required(['ADMIN'])
    def patch(self):
        data = request.get_json()
        category = Category.query.filter_by(cid=data.get("cid")).first()
        if(data.get("del_req")==False):
             category.request_deletion= False
             db.session.commit()
             return jsonify(" Category Deletion request rejected.")

        if (data.get("request_creation")==False):
            category.request_creation= False
            category.request_edit= False
            category.cname =  data.get("cname")
            db.session.commit()
            return jsonify(" CAT EDITED")

    

        category.cname =  data.get("cname")
        db.session.commit()
        return jsonify(" CAT EDITED")
       
class ProductResource(Resource):
    @jwt_required()
    def get(self,catid):
        data=[]
        category = Category.query.filter_by(cid=catid).all()
        if (Category):
                product = Product.query.filter_by(catid=catid).all()
                for item in product :
                    data.append({
                        'pname' : item .pname ,
                        'pid' : item .pid ,
                        'prate' : item .rateperunit,
                        'pquant' : item.quantity,
                        'punit' : item.unit ,
                        'product_deletion_req' : item.product_deletion_req,
                        'mfd_date':  str(item.mfd_date) ,
                        'expiry_date' : str(item.expiry_date),
                        'catid' : item.catid
                    })
              
                return   data
        else:
                return jsonify("CATEGORY NOT FOUND")
    @jwt_required()
    def post(self,catid):
        data = request.get_json()
        category = Category.query.filter_by(cid=catid)
        if( category):
            mfd= data.get('mfd_date') +' '+ '23:59:59'
            expiry =data.get('expiry_date')+' '+'23:59:59'
            mfd_date=datetime.strptime(mfd, '%Y-%m-%d %H:%M:%S')
            expiry_date=datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S')
            product =  Product(pname=data.get("pname"), pid=data.get("pid")  ,rateperunit=data.get("rateperunit") ,unit=data.get("unit"),quantity=data.get("quantity") ,mfd_date=mfd_date,
                               expiry_date=expiry_date,catid=catid,product_deletion_req=False,addedon=datetime.now(ist))
            db.session.add(product)
            db.session.commit()
            return jsonify("PRODUCT ADDED")
        else:
            abort(401, message="Category does not exist for the user")

    @jwt_required()        
    def put(self,catid):
        data = request.get_json()
       
        category = Category.query.filter_by(cid=data.get("catid")).first()
        if data.get("del_req")==True:
            product = Product.query.filter_by(pid=data.get("pid")).first()
            product.product_deletion_req = data.get("del_req")
            db.session.commit()
            return jsonify("Updated Deletion request of product")
        if data.get("del_req")==False:
            product = Product.query.filter_by(pid=data.get("pid")).first()
            product.product_deletion_req = data.get("del_req")
            db.session.commit()
            return jsonify("Deletion request cancel of product")

        if(category):
            product = Product.query.filter_by(pid=data.get("pid")).first()
            product.pname = data.get("pname")
            product.quantity =data.get("quantity")
            product.catid = data.get("catid")
            product.unit = data.get("punit")
            product.rateperunit = data.get("prate")
            # product.approved =data.get("approved")
            if data.get("approved") == "true":
                product.approved =True
            if data.get("approved") == "false":
                product.approved =False
            db.session.commit()
            return jsonify("CARD ADDED")
        else:
            abort(401, message="Category does not exist")

class ManageCategoryResource(Resource):
    @jwt_required()
    @role_required(['MJR'])
    def get(self):
        category = Category.query.all()
        data= []
        for category in category :
            data.append({
                'cid' : category.cid ,
                'cname' : category.cname ,
                'request_creation' : category.request_creation,
                'request_deletion' : category.request_deletion,
                # 'producta' : Product.pname.query.filter_by(catid =category.cid).all()
            })
     
        return data
    @jwt_required()
    def post(self):
        data = request.get_json()
        category =  Category(cname=data.get("category"),cid=data.get("cid"),request_creation=True)
        db.session.add(category)
        db.session.commit()
        return jsonify("Request Added")
  
    @jwt_required()
    def patch(self):
        data = request.get_json()
    
        category = Category.query.filter_by(cid=data.get("cid")).first()
        if data.get("request_deletion") == True:
            category.request_deletion = data.get("request_deletion")
        if data.get("request_edit") == True:
            category.request_edit = data.get("request_edit")
            category.newname = data.get("newname")
       
        category.cname =  data.get("cname")
        
     
        db.session.commit()
        return jsonify(" CAT EDITED")

class MemberResource(Resource):
    @jwt_required()
    def get(self):
        members = Member.query.filter_by(approved=False).all()
        data= []
        for member in members :
            data.append({
            
                'username' : member.username,
                'email' : member.email,
                'role' : member.role,
                # 'producta' : Product.pname.query.filter_by(catid =category.cid).all()
            })
     
        return data
    @jwt_required()
    def patch(self):
        data = request.get_json()
        member = Member.query.filter_by(email=data.get("email")).first()
        member.approved = True
     
        db.session.commit()
        return jsonify("Member Added")
    
    @jwt_required()
    def delete(self):
        data = request.get_json()
        member = Member.query.filter_by(email=data.get("email")).first()
        db.session.delete(member)     
        db.session.commit()
        return jsonify("Member Deleted")

class CartResource(Resource):
    @jwt_required()
    def get(self,email):
        cartlist=[]
        cart = Cart.query.filter_by(user_email=email).all()
        total=0
        for item in cart:
                product=Product.query.filter_by(pid=item.prodid).all()
                for product in product:
                    rate=product.rateperunit
                    name=product.pname
                    unit=product.unit
                    qaval=product.quantity
                    payableamount=int(rate)*int(item.qbought)
                    if  qaval >= item.qbought:
                        total=total+payableamount
                        unit=product.unit

                    category=Category.query.filter_by(cid=product.catid).first()
                    
                    category_name=category.cname
            
                cartlist.append({"category_name":category_name,"prodid":item.prodid,"payableamount":payableamount,"qaval":qaval,"qbought":item.qbought ,"pname":name,"rate":rate,"unit":unit})
        data=[]
        data.append(cartlist)
        data.append(total)
        return data
    
    @jwt_required()                
    def post(self,email):
        data=request.get_json()
        carts = Cart.query.filter_by(prodid=data.get("pid"),user_email=email).all()
        if(carts):
            for cart in carts:
                cart.qbought= int(cart.qbought) + int(data.get("qbought"))
                cart.totalamount= int(cart.totalamount) + int(data.get("totalamount"))
                db.session.commit()
            return jsonify("Cart Updated")
        if not carts:
            cartitem=Cart(prodid=data.get("pid"),qbought=data.get("qbought"),user_email=data.get("email"),totalamount=data.get("totalamount"))

            db.session.add(cartitem)
            db.session.commit()
            return jsonify("Item added to Cart")
        else:
            abort (401,message="Error in Post")


    @jwt_required()    
    def put(self,email):
        data=request.get_json()
        cart = Cart.query.filter_by(user_email=email).all()
        for item in cart:
            product = Product.query.filter_by(pid=item.prodid).first()
            if product.quantity >= item.qbought:
                product.quantity =product.quantity-item.qbought
                order=Orders(order_date=datetime.now(ist),user_email=email,pid_order=item.prodid,price_perunit=product.rateperunit,qbought=item.qbought)
                db.session.add(order)
                db.session.add(product)
                db.session.delete(item)
                db.session.commit()
        
        return jsonify("Order Placed")


    @jwt_required()
    def delete(self,email):
        data=request.get_json()
        cart = Cart.query.filter_by(prodid=data.get("prodid")).first()
        db.session.delete(cart)     
        db.session.commit()
        return jsonify("Item Deleted")
       
class LoginUserResource(Resource):
    def post(self):
        data = request.get_json()
     
        user = Member.query.filter_by(email=data['email']).first()
      
        if user.approved==False:
             return {'message': 'Invalid email or password'}, 401

        if user:
            # user = Member.query.filter_by(email=data['email'],role=data['role'],approved=True).first()
            user = Member.query.filter_by(email=data['email'],role=data['role']).first()
     
            if user and check_password_hash(user.password, data['password']):
                identity = {'email': user.email}

                # Generate an access token
                access_token = create_access_token(identity=identity, expires_delta=timedelta(2))
                return {'message': 'User logged in successfully', 'email':user.email,'access_token': access_token}

            return {'message': 'Invalid email or password'}, 401

        else:
            return render_template("signin.html")


        
@app.route("/",methods= ['GET'])

def signinpage():
    result= db.session.query(Category,Product).join(Product).all()
    return render_template("signin.html")
    

@app.route("/createmember" , methods=['POST'])  #api to add user cant put jwt.
def createmember():
    data = request.get_json()
    if data.get('email') :
        # If user already exists.

        if Member.query.filter_by(email=data['email']).first():
                return {'message': 'Already exists'}, 409
        if data['approved']==False:
            Userdata = Member(username=data.get("username", None), email=data.get("email", None),
                     password=generate_password_hash(data.get("password", None)),role=data.get("role"),active=True,approved=False)
            db.session.add(Userdata)
            db.session.commit()
            return jsonify("ADDED MANAGER REQUEST")
        else:

            Userdata = Member(username=data.get("username", None), email=data.get("email", None),
                        password=generate_password_hash(data.get("password", None)),role=data.get("role"),active=True,approved=True)
            db.session.add(Userdata)
            db.session.commit()
            return jsonify("ADDED")
# ADMIN ROLE REQUIRED

@app.route("/deletecategory/<cid>")
@jwt_required()
def delete_category(cid):
    category = Category.query.get(cid)
    db.session.delete(category)
    db.session.commit()
    return jsonify("Category Deleted")


#USER ROLE REQUIRED

@app.route("/getallproduct", methods=['GET'])
@jwt_required()
@role_required(['USER'])
def getallproduct():
    pdata = []
    product = Product.query.all()
    for product in product:
            mfd=str(product.mfd_date)
            expiry=str(product.expiry_date)
            pdata.append({
                        'pname' : product.pname ,
                        'pid' : product.pid ,
                        'prate' : product.rateperunit,
                        'pquant' : product.quantity,
                        'catid' : product.catid,
                        'mfd_date' :mfd,
                        'unit':product.unit,
                        'expiry_date':expiry,
                    })
  
    return pdata,200
#USER ROLE REQUIRED

@app.route("/getallcategory")
@jwt_required()
def getallcategory():
    category = Category.query.filter_by(request_deletion=False,request_creation=False).all()
    data= []
    for category in category :
        data.append({
            'cid' : category.cid ,
            'cname' : category.cname ,
            # 'producta' : Product.pname.query.filter_by(catid =category.cid).all()
        })
    return  data,200

# ADMIN ROLE REQUIRED
@app.route("/deleteproduct/<pid>")
@jwt_required()
def delete_product(pid):
    product = Product.query.get(pid)
    db.session.delete(product)
    db.session.commit()
    return jsonify("Product Deleted...")
#--------------------------------------------Search-----------------------------------------------
# user role
@app.route('/search/<keyword>', methods=['GET','POST'])  
@jwt_required()
def search(keyword):
    if request.method == 'GET':
        product_data=[]
        category_data=[]
        
        search = keyword
        query= "%"+search+"%"
        # Query the database to find matching data based on the search term
        results_product = Product.query.filter(Product.pname.like(query)).first()
        results_category = Category.query.filter(Category.cname.like(query)).first()
        results_product_2= Product.query.filter(Product.rateperunit.like(query)).first()

        
        
        if  results_product_2   :
             product_data.append({
                        'pname' : results_product_2.pname ,
                        'pid' : results_product_2.pid ,
                        'len' :2,
                    })
             return  product_data
        
        if  results_product  :
            product_data.append({
                        'pname' : results_product.pname ,
                        'pid' : results_product.pid ,
                        'cid' : results_product.catid,
                        'len':2,
                    })
            return  product_data
        
        if  results_category :
            product_cat=Product.query.filter_by(catid=results_category.cid).all()
            for product in product_cat:
                    category_data.append({
                            'cid'   :results_category.cid,
                            'cname' : results_category.cname ,
                            'pname' : product.pname ,
                            'pid' : product.pid ,
                            'len' :1
                        })
            return  category_data
       

        return jsonify("Nothing found")
#--------------------------------------------CELERY-----------------------------------------------

@celery.task(name="main.mailer")
def mailer(id):
    msg = Message("Grocery App", sender='alexeubank819@gmail.com', recipients=[id])
    msg.body = "Hi "+id+" "+"We have missed you!. Please visit the grocery app website to order your groceries and avail discounts"
    mail.send(msg)

@celery.task(name="main.create_csv")
def create_csv(data):
    df = pd.DataFrame(data)
    df.to_csv('./static/data.csv', header=True)
    print("done")

@celery.task(name="main.create_pdf_report")
def create_pdf_report(data,mail):
    with open("pdf.html") as  file_:
        template= Template(file_.read())
        message=  template.render(data=data)
  
    html= HTML(string=message)
    file_name=str(mail) + ".pdf"
    html.write_pdf(target=file_name)

@celery.task(name="main.pdf_mailer")
def pdf_mailer(id):
    file_name=str(id) + ".pdf"
    msg = Message("Grocery Store",  sender='alexeubank819@gmail.com', recipients=[id])
    msg.body = "Hi "+id+" This is your monthly report. Happy shopping"
    with app.open_resource('./'+file_name) as data:
        msg.attach(file_name, 'application/pdf', data.read())

    mail.send(msg)

@celery.task(name="main.monthly_report")
def monthly_report():
    users= Member.query.filter_by(role="USER").all()
    today = datetime.now()
    for user in users:
        data = []
        ords=Orders.query.filter_by(user_email=user.email).all()
        Totalexp=0
        for ord in ords:
            if(ord.order_date>= today - timedelta(days=30)):
                product_det=Product.query.filter_by(pid=ord.pid_order).first()
                bill=int(ord.qbought)*int(product_det.rateperunit)
                Totalexp=Totalexp+ bill
                data.append({
                    'product_name':product_det.pname,
                    'quantity_bought':str(ord.qbought)+str(product_det.unit),
                    'dop':str(ord.order_date),
                    'price':product_det.rateperunit,
                    'total':bill

                })
        data.append({"Total_expenditure":Totalexp})
        create_pdf_report(data,user.email)
        pdf_mail = pdf_mailer.delay(user.email)      


@celery.task(name="main.daily_remainder")
def daily_remainder():
    today = datetime.now()
    users= Member.query.filter_by(role="USER").all()
    order_list =[]
    for user in users:
        ords=Orders.query.filter_by(user_email=user.email).all()
        for ord in ords:
                if(ord.order_date >= today - timedelta(minutes=1440)):
                    order_list.append(ord.user_email)
                    break
    
    for user in users:
        if user.email in order_list:
            print(True)
        else:
            mail_job = mailer.delay(user.email)
    

    


    # if(ord.order_date>= today - timedelta(days=1)):

class ProductCSVRescource(Resource):
    
    
    @jwt_required()
    @role_required(['MJR'])
    def get(self, pid):
        today = datetime.now()
        product=Product.query.filter_by(pid=pid).first()
        ords=Orders.query.filter_by(pid_order=pid).all()
        unit_sold=0
        data = []
        for ord in ords:
          if(ord.order_date>= today - timedelta(days=30)):
            unit_sold=unit_sold+int(ord.qbought)
        data.append({
                        'Product name' : product.pname ,
                        'Product rate' : "Rs"+str(product.rateperunit)+" per "+str(product.unit),
                        'Quantity availabel' : str(product.quantity)+str(product.unit),
                        'Mfd date':  str(product.mfd_date) ,
                        'Expiry date' : str(product.expiry_date),
                        'Product sold in last 30days' : str(unit_sold)+str(product.unit)
                       
                    })
              
        create_csv(data)
        return {"Message": "CSV of prodyct created"}, 200
    

#-------------------------------------------------------------------------------------------------------------
api.add_resource(CartResource, "/cart/<email>")
api.add_resource(ProductResource,"/product/<int:catid>")
api.add_resource(CategoryResource, "/category")
api.add_resource(LoginUserResource, "/login")
api.add_resource(MemberResource, "/member")
api.add_resource(ManageCategoryResource,"/mcategory")
api.add_resource( ProductCSVRescource,"/productreport/<int:pid>")

if __name__ == "__main__" :
    with app.app_context(): 
        inspector = db.inspect(db.engine)
        table_names = inspector.get_table_names()
        if not table_names:  # If no tables exist
            db.create_all()
            adminUser = Member(username="ADMIN",email="admin@gmail.com",password=generate_password_hash("password"),role="ADMIN",active=True)
            db.session.add(adminUser)
            db.session.commit()
            print("Database tables created.")
        else:
            print("Database tables already exist.")
    app.run(debug =True)
