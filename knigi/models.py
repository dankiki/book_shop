import logging
from django.db.models import Model, CharField, ForeignKey, ManyToManyField, PositiveIntegerField, CASCADE, F

logger = logging.getLogger('django')


class Publisher(Model):
    name = CharField(max_length=250)

    def __str__(self):
        return self.name


class Item(Model):
    '''This is a base class for goods produced by publishers. Common info goes here'''
    publisher = ForeignKey(Publisher, related_name='items', on_delete=CASCADE)

    class Meta:
        abstract = True


class Book(Item):
    name = CharField(max_length=250)
    ISBN = CharField(max_length=13, blank=True)

    def __str__(self):
        return self.name


class Store(Model):
    name = CharField(max_length=250)
    books = ManyToManyField(Book, through='Inventory', blank=True)

    def __str__(self):
        return self.name

    def receive_shipment(self, payload):
        '''Receive JSON with a list of books and number of copies. Update the Inventory table.
        sample_json = [{"Title": "Pnin",
                        "Publisher": "Molodaya gvardia",
                        "Quantity": 1}]
        "Publisher" is not needed if the book is already present in the database
        '''
        for item in payload:
            in_stock = Inventory.objects.filter(store=self, book__name=item['Title'])
            if in_stock:
                in_stock.update(stock=F('stock') + item['Quantity'])
            else:
                try:
                    book = Book.objects.get(name=item['Title'])
                except Book.DoesNotExist:
                    if 'Publisher' in item.keys():
                        publisher, _ = Publisher.objects.get_or_create(name=item['Publisher'])
                        book = Book.objects.create(name=item['Title'], publisher=publisher)
                    else:
                        logger.error(f"Publisher is missing for the book {item['Title']}")
                        continue
                new_inventory = Inventory(book=book, store=self, stock=item['Quantity'])
                new_inventory.save()

    def sell_books(self, payload):
        '''Receive JSON with a list of books and number of copies sold. Update the Inventory table.
        sayload = [{"Title": "Pnin",
                "Quantity": 1},
               {"Title": "Lolita",
                "Quantity": 500},
               {"Title": "The Gift",
                "Quantity": 500}]
        Attempts to oversell a book should result in no change to its total number,
        attempts to sell a book not in stock should be ignored
        '''
        books_in_store = Inventory.objects.filter(store=self)
        titles_in_stock = dict(books_in_store.values_list('book__name', 'stock'))

        # two steps in order to avoid KeyError when querying for Quantity
        correctly_sold_temp = [(i['Title'], i['Quantity']) for i in payload if
                                         (i['Title'] in titles_in_stock.keys())]
        correctly_sold = [i for i in correctly_sold_temp if i[1] <= titles_in_stock[i[0]]]
        
        for i in correctly_sold:
            Inventory.objects.filter(store=self, book__name=i[0]).update(stock=F('stock') - i[1])


class Inventory(Model):
    sold = PositiveIntegerField(default=0, blank=True)
    stock = PositiveIntegerField(default=0, blank=True)
    book = ForeignKey(Book, on_delete=CASCADE)
    store = ForeignKey(Store, on_delete=CASCADE)

    def __str__(self):
        return f'Store {self.store}\nBook {self.book.name}\nSold {self.sold}\nStock {self.stock}'
