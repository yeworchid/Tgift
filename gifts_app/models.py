from django.db import models

class CollectionCache(models.Model):
    collection_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    image = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def to_dict(self):
        return {
            'id': self.collection_id,
            'name': self.name,
            'image': self.image
        }

class GiftCache(models.Model):
    collection_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    price = models.FloatField()  # Храним цену в TON как float
    image = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def to_dict(self):
        return {
            'name': self.name,
            'price': f"{self.price}",  # Оставляем конвертацию в рубли в views
            'image': self.image
        }