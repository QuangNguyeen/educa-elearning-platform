from django.db import models
from django.conf import settings

class Subscriber(models.Model):
    class Meta:
        abstract = True

    def update(self, event_type, data):
        raise NotImplementedError

class RoomSubscriber(Subscriber):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    publisher = models.ForeignKey('ChatPublisher', on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'publisher')
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user} subscribed to {self.publisher.name} since {self.joined_at}"

    def update(self, event_type, data):
        if event_type == "message":
            PublishedMessage.objects.create(publisher=self.publisher, user=self.user, content=data["content"])


class ChatPublisher(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.listeners = {}

    def __str__(self):
        return self.name

    def subscribe(self, event_type, subscriber):
        self.listeners.setdefault(event_type, [])
        if subscriber not in self.listeners[event_type]:
            self.listeners[event_type].append(subscriber)
            RoomSubscriber.objects.get_or_create(user=subscriber.user, publisher=self)

    def unsubscribe(self, event_type, subscriber):
        if event_type in self.listeners:
            self.listeners[event_type].remove(subscriber)
            RoomSubscriber.objects.filter(user=subscriber.user, publisher=self).delete()

    def notify(self, event_type, data):
        for subscriber in self.listeners.get(event_type, []):
            subscriber.update(event_type, data)

    def publish(self, content):
        self.listeners["message"] = list(self.roomsubscriber_set.all())
        self.notify("message", {"publisher": self, "content": content})


class PublishedMessage(models.Model):
    publisher = models.ForeignKey(ChatPublisher, related_name='messages', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.user} at {self.timestamp}: {self.content[:50]}..."
