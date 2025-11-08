// MongoDB 初始化脚本
/*
 * @Descripttion: 
 * @Author: ouchao
 * @Email: ouchao@sendpalm.com
 * @version: 1.0
 * @Date: 2025-04-03 17:34:12
 * @LastEditors: ouchao
 * @LastEditTime: 2025-04-03 17:46:41
 */
db = db.getSiblingDB('admin');

// 创建管理员用户
db.createUser({
  user: 'translate',
  pwd: 'ouchao',
  roles: [
    { role: 'userAdminAnyDatabase', db: 'admin' },
    { role: 'readWriteAnyDatabase', db: 'admin' },
    { role: 'dbAdminAnyDatabase', db: 'admin' },
    { role: 'clusterAdmin', db: 'admin' }
  ]
});

// 切换到应用数据库
db = db.getSiblingDB('translateai');

// 创建集合
db.createCollection('users');
db.createCollection('userfiles');
db.createCollection('orders');

// 添加测试记录（可选）
db.users.insertOne({
  name: 'TestUser',
  email: 'test@example.com',
  created_at: new Date()
});

print('MongoDB 初始化完成');