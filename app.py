import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, HiddenField, IntegerField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, NumberRange
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps # 用於 login_required
from datetime import datetime, timedelta
from wtforms.validators import Optional
from functools import wraps
DELIVERY_FEE = 30


app = Flask(__name__)

# 2. 修改 SECRET_KEY 設定：優先讀取環境變數，讀不到才用預設值
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '77ZPX8yHxujYpXz6aZkyAKm2kDCGt2zt')

# 3. 修改資料庫設定 (最重要的一步！)
# 這樣寫的意思是：如果 Render 有設定 'DATABASE_URL' 就用 Render 的(內網)，
# 如果沒有(例如你在自己電腦跑)，就用後面那串外部連線網址。
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://foodsheep_database_user:77ZPX8yHxujYpXz6aZkyAKm2kDCGt2zt@dpg-d5b6evv5r7bs73a6h0ng-a.virginia-postgres.render.com/foodsheep_database')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# 1. 資料庫模型 (Models) - 保持 Foodsheep 架構
# ==========================================
class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(100), nullable=False)
    user_email = db.Column(db.String(150), unique=True, nullable=False)
    user_password = db.Column(db.String(255), nullable=False)
    user_position = db.Column(db.String(255))
    user_identity = db.Column(db.String(20), nullable=False)
    user_contact = db.Column(db.String(50))
    is_vip = db.Column(db.Boolean, default=False)
    vip_expire_time = db.Column(db.DateTime, nullable=True)

class Food(db.Model):
    __tablename__ = 'foods'
    food_id = db.Column(db.Integer, primary_key=True)
    food_name = db.Column(db.String(100), nullable=False)
    food_price = db.Column(db.Integer, nullable=False)
    food_description = db.Column(db.Text)
    merchant_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    food_image = db.Column(db.String(500))

class Order(db.Model):
    __tablename__ = 'orders'
    order_id = db.Column(db.Integer, primary_key=True)
    merchant_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    order_cart = db.Column(ARRAY(db.Integer, dimensions=2))
    total_price = db.Column(db.Integer, nullable=False)
    order_time = db.Column(db.DateTime, default=datetime.utcnow)
    order_status = db.Column(db.String(50), default='pending')

# ==========================================
# 2. 表單定義 (Forms) - 參考你的檔案
# ==========================================

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('登入')

# 註冊表單
class RegistrationForm(FlaskForm):
    name = StringField('使用者名稱', validators=[DataRequired()])
    email = StringField('電子郵件', validators=[DataRequired(), Email()])
    password = PasswordField('密碼', validators=[DataRequired(), Length(min=6)])
    address = StringField('地址', validators=[DataRequired()])
    contact = StringField('聯絡電話', validators=[DataRequired()])
    identity = SelectField('身分', choices=[('customer', '顧客'), ('merchant', '商家')], validators=[DataRequired()])
    submit = SubmitField('註冊')

# 模擬下單表單
class SimpleOrderForm(FlaskForm):
    food_id = HiddenField('Food ID')
    quantity = IntegerField('數量', default=1, validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('立即購買')

class SettingsForm(FlaskForm):
    name = StringField('使用者名稱', validators=[DataRequired()])
    # Email 通常不建議隨意修改，或是需要驗證，這裡先設為唯讀顯示即可，不放在可編輯欄位
    contact = StringField('聯絡電話', validators=[DataRequired()])
    address = StringField('地址', validators=[DataRequired()]) # 對應資料庫的 user_position
    
    # 密碼欄位：如果不填寫代表不修改
    new_password = PasswordField('新密碼 (若不修改請留空)', validators=[Optional(), Length(min=6)])
    submit = SubmitField('儲存設定')

# ==========================================
# 2. 定義 Review 模型 (配合新的資料庫)
# ==========================================
class Review(db.Model):
    __tablename__ = 'reviews'  # 表格名稱改為 reviews
    review_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=False, unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    merchant_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    
    # ★ 欄位名稱變得很乾淨
    rating = db.Column(db.Integer, nullable=False) 
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# 3. 定義表單
# ==========================================
class ReviewForm(FlaskForm):
    rating = SelectField('評分', choices=[('5', '5星 - 非常滿意'), 
                                          ('4', '4星 - 滿意'), 
                                          ('3', '3星 - 普通'), 
                                          ('2', '2星 - 不滿意'), 
                                          ('1', '1星 - 非常糟糕')], validators=[DataRequired()])
    content = TextAreaField('心得評論', validators=[DataRequired()]) # 這裡對應 content
    submit = SubmitField('送出評價')

# ==========================================
# 3. 輔助功能 (Helpers)
# ==========================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('您必須先登入才能進行此操作！', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

class AddFoodForm(FlaskForm):
    name = StringField('餐點名稱', validators=[DataRequired()])
    price = IntegerField('價格', validators=[DataRequired(), NumberRange(min=1)])
    description = TextAreaField('餐點描述', validators=[DataRequired()])
    food_image = StringField('圖片網址 (請輸入 http 開頭的網址)')
    submit = SubmitField('確認上架')

# ==========================================
# 4. 路由邏輯 (Routes)
# ==========================================

# app.py

@app.route('/')
def index():
    if session.get('user_identity') == 'merchant':
        return redirect(url_for('merchant_menu'))
    
    # 1. 接收前端傳來的排序參數 (預設為 None)
    sort_order = request.args.get('sort') 

    merchants = User.query.filter_by(user_identity='merchant').all()
    
    merchant_list = []
    for m in merchants:
        # (這裡保持原本的圖片處理邏輯)
        cover_food = Food.query.filter_by(merchant_id=m.user_id).filter(Food.food_image != None).first()
        img_url = cover_food.food_image if (cover_food and cover_food.food_image) else 'https://www.shutterstock.com/shutterstock/videos/1093608713/thumb/7.jpg?ip=x480'
        
        # (這裡保持原本的評分計算邏輯)
        reviews = Review.query.filter_by(merchant_id=m.user_id).all()
        review_count = len(reviews)
        
        avg_rating = 0.0 # 預設浮點數
        if review_count > 0:
            total_stars = sum([r.rating for r in reviews])
            avg_rating = round(total_stars / review_count, 1)
            
        merchant_list.append({
            'id': m.user_id,
            'name': m.user_name,
            'address': m.user_position,
            'image': img_url,
            'rating': avg_rating,
            'review_count': review_count
        })
    
    # ★ 新增：根據 sort_order 進行排序
    if sort_order == 'desc':
        # 降冪 (高 -> 低)：reverse=True
        merchant_list.sort(key=lambda x: x['rating'], reverse=True)
    elif sort_order == 'asc':
        # 升冪 (低 -> 高)：reverse=False
        merchant_list.sort(key=lambda x: x['rating'], reverse=False)
    # 如果沒傳參數，就維持原本的 ID 順序
        
    return render_template('index.html', merchants=merchant_list, current_sort=sort_order)


# app.py

# ★ 新增：登入功能
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        
        # 這裡假設資料庫欄位是 user_email 和 user_password
        user = User.query.filter_by(user_email=email).first()
        
        if user and check_password_hash(user.user_password, password):
            # 登入成功，將資料寫入 Session
            session['user_id'] = user.user_id
            session['user_name'] = user.user_name
            session['user_identity'] = user.user_identity
            
            # ★★★ 關鍵修正：補上這一行！ ★★★
            # 將資料庫裡的 VIP 狀態也存進 Session，這樣 base.html 才讀得到
            session['is_vip'] = user.is_vip
            
            flash(f'歡迎回來，{user.user_name}！', 'success')
            
            # 如果是商家，導向商家後台；否則導向首頁
            if user.user_identity == 'merchant':
                return redirect(url_for('merchant_menu'))
            else:
                return redirect(url_for('index'))
        else:
            flash('登入失敗，請檢查 Email 或密碼。', 'danger')
            
    return render_template('login.html', form=form)

# ★ 舊的 dashboard 路由可以改成「導向訂單頁面」，或是直接拿掉
@app.route('/merchant')
@login_required
def merchant_dashboard():
    return redirect(url_for('merchant_orders'))

# ★ 新增：專門管理訂單的頁面
@app.route('/merchant/orders')
@login_required
def merchant_orders():
    if session.get('user_identity') != 'merchant':
        return redirect(url_for('index'))

    # 只撈取訂單相關資料
    my_orders = Order.query.filter_by(merchant_id=session['user_id']).order_by(Order.order_time.desc()).all()
    
    # 準備訂單顯示需要的關聯資料
    food_ids = set()
    customer_ids = set()
    for o in my_orders:
        customer_ids.add(o.customer_id)
        if o.order_cart:
            for item in o.order_cart:
                food_ids.add(item[0])
                
    foods = Food.query.filter(Food.food_id.in_(food_ids)).all()
    food_map = {f.food_id: f for f in foods}
    
    customers = User.query.filter(User.user_id.in_(customer_ids)).all()
    customer_map = {u.user_id: u for u in customers}

    return render_template('merchant_orders.html', 
                           orders=my_orders, 
                           food_map=food_map, 
                           customer_map=customer_map)

# ★ 新增：專門管理菜單的頁面
@app.route('/merchant/menu')
@login_required
def merchant_menu():
    if session.get('user_identity') != 'merchant':
        return redirect(url_for('index'))

    # 只撈取菜單資料
    my_foods = Food.query.filter_by(merchant_id=session['user_id']).all()
    
    return render_template('merchant_menu.html', foods=my_foods)

# ★ 新增：商家操作訂單 (接單 / 完成 / 拒絕)
@app.route('/merchant/order/<int:order_id>/<action>')
@login_required
def merchant_order_action(order_id, action):
    # 驗證是否為商家
    if session.get('user_identity') != 'merchant':
        return redirect(url_for('index'))
        
    order = Order.query.get_or_404(order_id)
    
    # 驗證這筆訂單是否屬於該商家 (防止誤改別人的單)
    if order.merchant_id != session['user_id']:
        flash('權限不足', 'danger')
        return redirect(url_for('merchant_dashboard'))
        
    # 狀態機邏輯
    if action == 'accept':
        order.order_status = 'accepted' # 接單 (製作中)
        flash(f'訂單 #{order_id} 已接單！', 'success')
    elif action == 'complete':
        order.order_status = 'completed' # 完成
        flash(f'訂單 #{order_id} 已完成並送達！', 'success')
    elif action == 'reject':
        order.order_status = 'rejected' # 拒絕
        flash(f'訂單 #{order_id} 已拒絕。', 'warning')
        
    db.session.commit()
    return redirect(url_for('merchant_dashboard'))

# ★ 新增：顧客取消訂單
@app.route('/customer/cancel/<int:order_id>')
@login_required
def customer_cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # 驗證是否為該訂單的主人
    if order.customer_id != session['user_id']:
        flash('權限不足', 'danger')
        return redirect(url_for('my_orders'))
        
    # 只有 "pending" (未接單) 的狀態才能取消
    if order.order_status == 'pending':
        order.order_status = 'cancelled'
        db.session.commit()
        flash(f'訂單 #{order_id} 已成功取消。', 'success')
    else:
        flash('商家已接單或訂單已結束，無法取消。', 'danger')
        
    return redirect(url_for('my_orders'))

# ★ 新增：上架商品功能
@app.route('/add_food', methods=['GET', 'POST'])
@login_required
def add_food():
    if session.get('user_identity') != 'merchant':
        return redirect(url_for('index'))

    form = AddFoodForm()
    if form.validate_on_submit():
        new_food = Food(
            food_name=form.name.data,
            food_price=form.price.data,
            food_description=form.description.data,
            merchant_id=session['user_id'],
            food_image=form.food_image.data 
        )
        db.session.add(new_food)
        db.session.commit()
        flash('商品上架成功！', 'success')
        return redirect(url_for('merchant_menu'))

    return render_template('add_food.html', form=form)

# ★ 新增：編輯商品路由
@app.route('/merchant/edit_food/<int:food_id>', methods=['GET', 'POST'])
@login_required
def edit_food(food_id):
    # 1. 撈取商品資料
    food = Food.query.get_or_404(food_id)
    
    # 2. 安全檢查：確認這商品是該商家的
    if food.merchant_id != session['user_id']:
        flash('權限不足：您無法編輯其他商家的商品', 'danger')
        return redirect(url_for('merchant_menu'))
    
    form = AddFoodForm()
    
    # 3. 處理表單提交 (POST)
    if form.validate_on_submit():
        # 更新資料庫欄位
        food.food_name = form.name.data
        food.food_price = form.price.data
        food.food_description = form.description.data
        food.food_image = form.food_image.data
        
        db.session.commit()
        flash(f'商品「{food.food_name}」更新成功！', 'success')
        return redirect(url_for('merchant_menu'))
    
    # 4. 處理頁面顯示 (GET) - 預先填入舊資料
    if request.method == 'GET':
        form.name.data = food.food_name
        form.price.data = food.food_price
        form.description.data = food.food_description
        form.food_image.data = food.food_image

    return render_template('edit_food.html', form=form, food=food)

# ★ 新增：刪除商品路由
@app.route('/merchant/delete_food/<int:food_id>')
@login_required
def delete_food(food_id):
    food = Food.query.get_or_404(food_id)
    
    # 安全檢查
    if food.merchant_id != session['user_id']:
        flash('權限不足', 'danger')
        return redirect(url_for('merchant_menu'))
        
    try:
        db.session.delete(food)
        db.session.commit()
        flash('商品已刪除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗 (可能該商品已有訂單紀錄)：{e}', 'danger')
        
    return redirect(url_for('merchant_menu'))

# ★ 新增：登出功能
@app.route('/logout')
def logout():
    session.clear()
    flash('您已成功登出。', 'info')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        # 檢查 Email 是否重複
        if User.query.filter_by(user_email=form.email.data).first():
            flash('此 Email 已被註冊！', 'danger')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(form.password.data)
        new_user = User(
            user_name=form.name.data,
            user_email=form.email.data,
            user_password=hashed_pw,
            user_position=form.address.data,
            user_contact=form.contact.data,
            user_identity=form.identity.data
        )
        db.session.add(new_user)
        db.session.commit()
        flash('註冊成功！請登入。', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html', form=form)

# 購買路由 (加上 @login_required 保護)
@app.route('/buy/<int:food_id>', methods=['GET', 'POST'])
@login_required 
def buy_food(food_id):
    target_food = Food.query.get_or_404(food_id)
    form = SimpleOrderForm()
    form.food_id.data = food_id 
    
    if form.validate_on_submit():
        qty = form.quantity.data
        total = target_food.food_price * qty
        cart_data = [[target_food.food_id, qty]]
        
        new_order = Order(
            merchant_id=target_food.merchant_id,
            customer_id=session['user_id'], # 使用 Session 中的 ID
            total_price=total,
            order_cart=cart_data
        )
        db.session.add(new_order)
        db.session.commit()
        flash('訂單已送出！商家正在確認中。', 'success')
        return redirect(url_for('my_orders'))
        
    return render_template('booking.html', form=form, food=target_food) # 這裡借用 booking.html 作為確認頁

# ==========================================
# 購物車功能 (Cart Routes)
# ==========================================

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    # 1. 直接從 HTML 表單抓取資料
    # 對應 shop.html 裡的 name="food_id" 和 name="quantity"
    food_id = request.form.get('food_id')
    quantity = request.form.get('quantity')
    
    # 除錯用：印出來看看有沒有收到資料 (會在下方的終端機顯示)
    print(f"嘗試加入購物車: ID={food_id}, Qty={quantity}")

    if food_id and quantity:
        food_id = int(food_id)
        quantity = int(quantity)
        
        # 2. 初始化購物車
        if 'cart' not in session:
            session['cart'] = []
            
        cart = session['cart']
        
        # 3. 檢查是否已存在，有則加數量
        found = False
        for order_item in cart:
            if order_item['food_id'] == food_id:
                order_item['qty'] += quantity
                found = True
                break
        
        # 4. 沒有則新增
        if not found:
            cart.append({'food_id': food_id, 'qty': quantity})
            
        # ★ 非常重要：告訴 Flask session 內容變了，請存檔
        session.modified = True
        
        flash(f'已加入購物車！目前數量：{quantity}', 'success')
    else:
        flash('加入失敗，資料不完整', 'danger')
        
    # 導回上一頁 (使用者原本在哪個商家頁面，就回哪裡)
    return redirect(request.referrer or url_for('index'))

# app.py

@app.route('/cart')
def view_cart():
    if 'cart' not in session or not session['cart']:
        return render_template('cart.html', cart_groups={}, total_final=0)
    
    cart = session['cart']
    cart_groups = {}
    total_final = 0
    
    # 判斷是否為 VIP
    is_vip = session.get('is_vip', False)
    
    # 預設外送費原價 (如果你的 User 資料表有 delivery_fee 欄位，請改成 merchant.delivery_fee)
    DEFAULT_FEE = 30
    
    # 1. 整理購物車與計算
    for item in cart:
        food_id = item.get('food_id')
        qty = item.get('qty', 0)
        
        food = Food.query.get(food_id)
        if not food:
            continue
            
        merchant = User.query.get(food.merchant_id)
        
        if merchant.user_id not in cart_groups:
            # 初始化該商家的購物車群組
            cart_groups[merchant.user_id] = {
                'merchant_name': merchant.user_name,
                'order_items': [],
                'subtotal': 0,
                # 設定運費邏輯
                'delivery_fee_original': DEFAULT_FEE,
                'delivery_fee_final': 0 if is_vip else DEFAULT_FEE,
                'discount': 0,         # 新增：該商家的折扣金額
                'total_with_fee': 0
            }
        
        # 加入商品
        cart_groups[merchant.user_id]['order_items'].append({
            'food_id': food.food_id,
            'food_name': food.food_name,
            'price': food.food_price,
            'qty': qty,
            'image': food.food_image
        })
        
        # 累加商品小計
        cart_groups[merchant.user_id]['subtotal'] += food.food_price * qty

    # 2. 計算每個商家的最終金額 (含運費與折扣)
    for mid, group in cart_groups.items():
        # A. 計算 VIP 滿額折扣 (單一商家滿 1000 打 95 折)
        if is_vip and group['subtotal'] >= 1000:
            group['discount'] = int(group['subtotal'] * 0.05)
        
        # B. 計算該單總額 = 小計 + 最終運費 - 折扣
        group['total_with_fee'] = group['subtotal'] + group['delivery_fee_final'] - group['discount']
        
        # C. 累加到整台購物車的總金額
        total_final += group['total_with_fee']
    
    # 注意：這裡不再傳送 global 的 discount_amount，因為已經分散到各商家了
    return render_template('cart.html', 
                         cart_groups=cart_groups, 
                         total_final=total_final)


@app.route('/update_cart_item', methods=['POST'])
def update_cart_item():
    food_id = int(request.form.get('food_id'))
    change = int(request.form.get('change')) # +1 或 -1
    
    if 'cart' in session:
        cart = session['cart']
        new_cart = []
        
        for item in cart:
            # 使用 .get() 確保讀取字典格式，避免 KeyError
            current_id = item.get('food_id')
            
            if current_id == food_id:
                # 判斷鍵名是 quantity 還是 qty
                qty_key = 'quantity' if 'quantity' in item else 'qty'
                
                if qty_key in item:
                    item[qty_key] += change
                    
                    # 數量 > 0 才保留
                    if item[qty_key] > 0:
                        new_cart.append(item)
            else:
                new_cart.append(item)
        
        session['cart'] = new_cart
        session.modified = True
        
    # ★ 修改這裡：原本是 'cart'，改成 'view_cart'
    return redirect(url_for('view_cart'))


@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('index'))
        
    cart = session['cart']
    # 1. 撈出購物車內所有商品的資料
    food_ids = [item['food_id'] for item in cart]
    foods = Food.query.filter(Food.food_id.in_(food_ids)).all()
    food_map = {f.food_id: f for f in foods}
    
    orders_to_create = {}
    
    # 2. 將商品依照商家 (mid) 分組並計算小計
    for item in cart:
        fid = item['food_id']
        qty = item['qty']
        food = food_map.get(fid)
        if not food: continue
        
        mid = food.merchant_id
        if mid not in orders_to_create:
            orders_to_create[mid] = {'subtotal': 0, 'cart_data': []}
        
        cost = food.food_price * qty
        orders_to_create[mid]['subtotal'] += cost
        orders_to_create[mid]['cart_data'].append([fid, qty])

    # 紀錄新建立的訂單，稍後傳給前端顯示
    new_orders = []
    
    # ★ 新增：取得 VIP 狀態
    is_vip = session.get('is_vip', False)

    try:
        for mid, data in orders_to_create.items():
            subtotal = data['subtotal']
            
            # --- ★★★ VIP 優惠計算邏輯 (新增部分) ★★★ ---
            
            # 1. 取得該商家的運費設定 (如果沒設定，預設為 60)
            # 為了保險，我們先抓出商家物件
            merchant = User.query.get(mid)
            original_fee = getattr(merchant, 'delivery_fee', 60) 
            
            # 2. 判斷運費
            if is_vip:
                delivery_fee = 0 # VIP 免運
            else:
                delivery_fee = original_fee
            
            # 3. 判斷滿額折扣
            discount = 0
            if is_vip and subtotal >= 1000:
                discount = int(subtotal * 0.05) # 5% 折扣
            
            # 4. 計算最終金額
            final_price = subtotal + delivery_fee - discount
            
            # ---------------------------------------------
            
            new_order = Order(
                merchant_id=mid,
                customer_id=session['user_id'],
                total_price=final_price, # 這裡存入的就會是扣掉優惠後的價格
                order_cart=data['cart_data'],
                order_status='pending'
            )
            db.session.add(new_order)
            new_orders.append(new_order) 
            
        db.session.commit() # 存入資料庫
        
        session.pop('cart', None) # 清空購物車
        
        # 撈一下商家資料給前端顯示用
        merchant_ids = list(orders_to_create.keys())
        merchants = User.query.filter(User.user_id.in_(merchant_ids)).all()
        merchant_map = {m.user_id: m for m in merchants}
        
        return render_template('order_confirmation.html', 
                             orders=new_orders, 
                             food_map=food_map, 
                             merchant_map=merchant_map,
                             is_vip=is_vip) # 多傳一個 is_vip 給前端，方便顯示文字
        
    except Exception as e:
        db.session.rollback()
        print(e) # 印出錯誤以便除錯
        flash(f'結帳失敗：{e}', 'danger')
        return redirect(url_for('view_cart'))
    

# 1. 單項刪除路由
@app.route('/remove_cart_item/<int:food_id>')
def remove_cart_item(food_id):
    if 'cart' in session:
        cart = session['cart']
        # 使用 List Comprehension 快速過濾
        # 只保留 "food_id 不等於 目標ID" 的商品
        # item.get('food_id') 是為了配合之前修好的字典格式
        new_cart = [item for item in cart if item.get('food_id') != food_id]
        
        session['cart'] = new_cart
        session.modified = True
        
    return redirect(url_for('view_cart'))


@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None) # 清除 session
    
    # 這裡可以保留你的提示訊息，這樣畫面會跳出「購物車已清空」的通知，體驗更好
    flash('購物車已清空', 'info') 
    
    # ★ 建議改成導向回 'view_cart'
    # 這樣使用者才會看到 cart.html 裡面那個漂亮的 "購物車是空的" 畫面
    return redirect(url_for('view_cart'))

@app.route('/add_review/<int:order_id>', methods=['GET', 'POST'])
@login_required
def add_review(order_id):
    order = Order.query.get_or_404(order_id)
    
    # 權限檢查
    if order.customer_id != session['user_id']:
        return redirect(url_for('my_orders'))
    if order.order_status != 'completed':
        flash('訂單尚未完成，無法評論', 'warning')
        return redirect(url_for('my_orders'))
        
    # 檢查是否已評論 (改用 Review 模型查詢)
    existing = Review.query.filter_by(order_id=order_id).first()
    if existing:
        flash('您已經評論過此訂單', 'info')
        return redirect(url_for('my_orders'))

    form = ReviewForm()
    if form.validate_on_submit():
        new_review = Review(
            order_id=order_id,
            customer_id=session['user_id'],
            merchant_id=order.merchant_id,
            # ★ 存入資料庫 (欄位變簡單了)
            rating=int(form.rating.data),
            content=form.content.data
        )
        db.session.add(new_review)
        db.session.commit()
        flash('感謝您的評價！', 'success')
        return redirect(url_for('merchant_shop', merchant_id=order.merchant_id))

    return render_template('add_review.html', form=form, order=order)

# ==========================================
# 5. 路由：我的訂單 (my_orders)
# ==========================================
@app.route('/my_orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(customer_id=session['user_id']).order_by(Order.order_time.desc()).all()
    
    # ★ 改用 Review 查詢
    my_reviews = Review.query.filter_by(customer_id=session['user_id']).all()
    reviewed_order_ids = [r.order_id for r in my_reviews] 

    # (原本的 food_map, merchant_map 邏輯保持不變，省略...)
    # ... 記得這裡要把上面的 food_map 等程式碼補齊 ...
    
    # 這裡只列出需要改動的部分，其他不變
    all_food_ids = set()
    for order in orders:
        if order.order_cart:
            for item in order.order_cart:
                all_food_ids.add(item[0])
    foods = Food.query.filter(Food.food_id.in_(all_food_ids)).all()
    food_map = {f.food_id: f for f in foods}
    merchants = User.query.filter_by(user_identity='merchant').all()
    merchant_map = {m.user_id: m for m in merchants}

    return render_template('my_orders.html', 
                           orders=orders, 
                           food_map=food_map, 
                           merchant_map=merchant_map,
                           reviewed_order_ids=reviewed_order_ids)

# ==========================================
# 6. 路由：商家首頁 (shop)
# ==========================================
@app.route('/shop/<int:merchant_id>')
def merchant_shop(merchant_id):
    merchant = User.query.get_or_404(merchant_id)
    foods = Food.query.filter_by(merchant_id=merchant_id).all()
    
    # ★ 改用 Review 查詢
    reviews = Review.query.filter_by(merchant_id=merchant_id).order_by(Review.created_at.desc()).all()
    
    avg_rating = 0
    if reviews:
        # ★ 這裡改成 r.rating
        total = sum([r.rating for r in reviews])
        avg_rating = round(total / len(reviews), 1)
        
    customer_ids = [r.customer_id for r in reviews]
    customers = User.query.filter(User.user_id.in_(customer_ids)).all()
    user_map = {u.user_id: u for u in customers}

    return render_template('shop.html', 
                           merchant=merchant, 
                           foods=foods,
                           reviews=reviews,       
                           avg_rating=avg_rating, 
                           user_map=user_map)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = User.query.get(session['user_id'])
    form = SettingsForm()

    if form.validate_on_submit():
        # 更新資料
        user.user_name = form.name.data
        user.user_contact = form.contact.data
        user.user_position = form.address.data
        
        # 如果有輸入新密碼才更新
        if form.new_password.data:
            user.user_password = generate_password_hash(form.new_password.data)
            
        db.session.commit()
        
        # 更新 session 中的名稱，以免導覽列顯示舊名字
        session['user_name'] = user.user_name
        
        flash('個人資料已更新！', 'success')
        return redirect(url_for('settings'))

    # GET 請求時，預先填入舊資料
    if request.method == 'GET':
        form.name.data = user.user_name
        form.contact.data = user.user_contact
        form.address.data = user.user_position

    # 如果是商家，計算一下目前的平均評分 (對應你的截圖需求 user_rating)
    current_rating = "無評分"
    if user.user_identity == 'merchant':
        reviews = Review.query.filter_by(merchant_id=user.user_id).all()
        if reviews:
            total = sum([r.rating for r in reviews])
            avg = round(total / len(reviews), 1)
            current_rating = f"{avg} ★"
        else:
            current_rating = "尚未收到評價"

    return render_template('settings.html', form=form, user=user, rating=current_rating)

@app.route('/merchant/reviews')
@login_required
def merchant_reviews():
    # 1. 權限檢查：只有商家能看
    if session.get('user_identity') != 'merchant':
        return redirect(url_for('index'))

    # 2. 撈取該商家的所有評論 (依時間倒序)
    reviews = Review.query.filter_by(merchant_id=session['user_id']).order_by(Review.created_at.desc()).all()

    # 3. 計算平均分數 (為了符合你要的 header 樣式)
    avg_rating = 0
    if reviews:
        total_score = sum([r.rating for r in reviews])
        avg_rating = round(total_score / len(reviews), 1)

    # 4. 撈取評論者的名字 (因為 Review 表只有 customer_id)
    customer_ids = [r.customer_id for r in reviews]
    customers = User.query.filter(User.user_id.in_(customer_ids)).all()
    customer_map = {u.user_id: u for u in customers}

    return render_template('merchant_reviews.html', 
                           reviews=reviews, 
                           avg_rating=avg_rating,
                           customer_map=customer_map)


# --- 會員升級頁面 ---
@app.route('/upgrade')
@login_required
def upgrade_page():
    # 1. ★ 修正：先從 session 拿 ID，再去資料庫抓人
    user_id = session.get('user_id')
    user = User.query.get(user_id) 
    # 現在這個 'user' 變數就是當前使用者了

    # 2. 檢查是否已是會員且未過期 (把原本的 current_user 改成 user)
    if user.is_vip and user.vip_expire_time:
        if user.vip_expire_time > datetime.now():
            # 如果已經是會員，計算剩餘天數
            remaining = (user.vip_expire_time - datetime.now()).days
            flash(f'您已經是尊榮會員！剩餘天數：{remaining} 天', 'info')
    
    # 3. ★ 關鍵：傳送給 HTML 時，把 user 變數取名為 current_user
    # 這樣你的 upgrade.html 就不會報錯
    return render_template('upgrade.html', current_user=user)

# --- 處理升級動作 (模擬付款) ---
@app.route('/process_upgrade', methods=['POST'])
@login_required
def process_upgrade():
    # 1. ★ 修正：一樣先抓人
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # 2. 更新 VIP 狀態
    user.is_vip = True
    # 設定到期日 (從現在開始 +30 天)
    user.vip_expire_time = datetime.now() + timedelta(days=30)
    db.session.commit()
    # 3. ★ 補上這行：更新 session，這樣導覽列的皇冠才會立刻出現
    session['is_vip'] = True
    
    flash('🎉 恭喜！您已升級為尊榮會員，享有免運與折扣優惠！', 'success')
    return redirect(url_for('index'))


@app.context_processor
def inject_user():
    user = None
    if 'user_id' in session:
        # 如果 session 裡有 user_id，就去資料庫把整個人抓出來
        user = User.query.get(session['user_id'])
    
    # 回傳給所有 template 使用
    return dict(current_user=user)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('請先登入', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)