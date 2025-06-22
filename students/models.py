from abc import ABC, abstractmethod
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.db import models

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.user.username} - {self.class_name}"

class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.user.username} - {self.department}"

# INTERFACE
class UserInterface(ABC):
    @abstractmethod
    def getUsername(self) -> str: pass

    @abstractmethod
    def getEmail(self) -> str: pass

    @abstractmethod
    def save(self) -> dict: pass

# Student Concrete Product
class StudentUser(UserInterface):
    def __init__(self, username: str, email: str, password: str, class_name: str):
        self.user = User(
            username=username,
            email=email,
            password=make_password(password),
            is_active=True,
            is_staff=False,
            is_superuser=False
        )
        self.class_name = class_name

    def getUsername(self) -> str:
        return self.user.username

    def getEmail(self) -> str:
        return self.user.email

    def save(self) -> dict:
        self.user.save()
        Student.objects.create(user=self.user, class_name=self.class_name)
        return {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": "student",
            "class_name": self.class_name
        }

# Teacher Concrete Product
class TeacherUser(UserInterface):
    def __init__(self, username: str, email: str, password: str, department: str):
        self.user = User(
            username=username,
            email=email,
            password=make_password(password),
            is_active=True,
            is_staff=True,
            is_superuser=False
        )
        self.department = department

    def getUsername(self) -> str:
        return self.user.username

    def getEmail(self) -> str:
        return self.user.email

    def save(self) -> dict:
        self.user.save()
        Teacher.objects.create(user=self.user, department=self.department)
        return {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": "teacher",
            "department": self.department
        }

# FACTORIES
class UserFactory(ABC):
    @abstractmethod
    def createUser(self, username: str, email: str, password: str, **kwargs) -> UserInterface:
        pass

class StudentFactory(UserFactory):
    def createUser(self, username: str, email: str, password: str, **kwargs) -> UserInterface:
        return StudentUser(username, email, password, class_name=kwargs['class_name'])

class TeacherFactory(UserFactory):
    def createUser(self, username: str, email: str, password: str, **kwargs) -> UserInterface:
        return TeacherUser(username, email, password, department=kwargs['department'])

# CRUD OPERATIONS
class UserOperation(ABC):
    @abstractmethod
    def execute(self, data: dict) -> any: pass

class CreateUser(UserOperation):
    def execute(self, data):
        user_type = data['type']
        if user_type == 'student':
            factory = StudentFactory()
            user = factory.createUser(
                username=data['username'],
                email=data['email'],
                password=data['password'],
                class_name=data['class_name']
            )
        elif user_type == 'teacher':
            factory = TeacherFactory()
            user = factory.createUser(
                username=data['username'],
                email=data['email'],
                password=data['password'],
                department=data['department']
            )
        else:
            raise ValueError("Loại người dùng không hợp lệ.")
        return user.save()


class UpdateUser(UserOperation):
    def execute(self, data):
        user = User.objects.get(id=data['id'])

        # Các field cơ bản
        for field in ['username', 'email', 'is_active', 'is_staff', 'first_name', 'last_name']:
            if field in data:
                setattr(user, field, data[field])

        if 'password' in data:
            user.password = make_password(data['password'])

        user.save()

        # Cập nhật thông tin phụ
        extra = {}
        if hasattr(user, 'student') and 'class_name' in data:
            user.student.class_name = data['class_name']
            user.student.save()
            extra = {"role": "student", "class_name": user.student.class_name}
        elif hasattr(user, 'teacher') and 'department' in data:
            user.teacher.department = data['department']
            user.teacher.save()
            extra = {"role": "teacher", "department": user.teacher.department}

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "is_staff": user.is_staff,
            **extra
        }


class DeleteUser(UserOperation):
    def execute(self, data):
        user = User.objects.get(id=data['id'])
        username = user.username
        user.delete()
        return {"message": f"Đã xóa người dùng {username}"}

class SearchUser(UserOperation):
    def execute(self, data):
        query = data.get('query', '')
        results = User.objects.filter(username__icontains=query)
        return list(results.values('id', 'username', 'email', 'is_staff'))

# OPERATION FACTORY
class UserOperationFactory:
    @staticmethod
    def get_operation(action: str) -> UserOperation:
        match action:
            case 'create': return CreateUser()
            case 'update': return UpdateUser()
            case 'delete': return DeleteUser()
            case 'search': return SearchUser()
            case _: raise ValueError("Hành động không hợp lệ.")
