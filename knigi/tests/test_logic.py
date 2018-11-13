import pytest
import operator
import pdb
from collections import namedtuple
from functools import reduce
from pytest import fixture
from django.db.models import Q, Sum
from knigi.models import Book, Store, Publisher, Inventory

pytestmark = pytest.mark.django_db


@fixture
def create_everybody():
    publisher = Publisher.objects.create(name='Sovetisch heimland')
    store = Store.objects.create(name='Dom knigi')
    TestData = namedtuple('TestData', ['publisher', 'store'])
    return TestData(publisher, store)


def test_fixture(create_everybody):
    publisher, store = create_everybody
    assert publisher.name == 'Sovetisch heimland'
    assert store.name == 'Dom knigi'


def util_count_received(payload, store):
    '''Helper function to calculate the total number of books in stock after 
    shipment arrives. Premises:
    - Every new book should have a publisher
    '''
    # Counting unique titles
    books_in_store = Inventory.objects.filter(store=store)
    titles_in_stock = books_in_store.values_list('book__name', flat=True)
    correctly_shipped = [(i['Title'], i['Quantity']) for i in payload if 
                                                         (i['Title'] in titles_in_stock) or
                                                         ('Publisher' in i.keys())]
    received_titles = [i[0] for i in correctly_shipped]
    received_titles.extend(titles_in_stock)
    total_unique_titles = len(set(received_titles))
    
    # Counting total items in store after shipment is received
    books_in_store = Inventory.objects.filter(store=store).aggregate(Sum('stock'))['stock__sum']
    books_received = sum([i[1] for i in correctly_shipped])
    if books_in_store:
        items = books_in_store + books_received
    else:
        items = books_received

    TotalCount = namedtuple('TotalCount', ['titles', 'items'])
    return TotalCount(total_unique_titles, items)


def util_count_sold(payload, store):
    '''Helper function to calculate the number of books in stock after some are sold.
    Attempts to oversell a book should result in no change to its total number,
    attempts to sell a book not in stock should be ignored'''
    books_in_store = Inventory.objects.filter(store=store)
    titles_in_stock = dict(books_in_store.values_list('book__name', 'stock'))

    # two steps in order to avoid KeyError when querying for Quantity
    correctly_sold_temp = [(i['Title'], i['Quantity']) for i in payload if
                                         (i['Title'] in titles_in_stock.keys())]
    correctly_sold = [i for i in correctly_sold_temp if i[1] <= titles_in_stock[i[0]]]

    for i in correctly_sold:
        titles_in_stock[i[0]] -= i[1]
    
    return titles_in_stock
    



def test_receive_shipment(create_everybody, caplog):
    publisher, store = create_everybody
    # Test books that are not in stock yet
    payload = [{"Title": "Pnin",
                "Publisher": "Molodaya gvardia",
                "Quantity": 1},
               {"Title": "Lolita",
                "Publisher": "Molodaya gvardia",
                "Quantity": 10}]

    books_in_store = Inventory.objects.filter(store=store)
 
    assert books_in_store.count() == 0  #We start with an empty store

    total_unique_titles, total_items = util_count_received(store=store,
                                                  payload=payload)
    store.receive_shipment(payload=payload) # Add books to the store

    # Test that inventory was increased and the count was correct
    assert books_in_store.all().count() == total_unique_titles
    assert books_in_store.aggregate(Sum('stock'))['stock__sum'] == total_items

    # Send the second shipment and test that number of books already in stock
    # is correctly increased
    total_unique_titles, total_items = util_count_received(store=store,
                                                  payload=payload)
    store.receive_shipment(payload=payload)
    assert books_in_store.all().count() == total_unique_titles
    assert books_in_store.aggregate(Sum('stock'))['stock__sum'] == total_items

    # Send a new book with no publisher specified
    payload = [{"Title": "Speak memory",
                "Quantity": 1},
               {"Title": "Lolita",
                "Publisher": "Molodaya gvardia",
                "Quantity": 10}]
    
    total_unique_titles, total_items = util_count_received(store=store,
                                                  payload=payload)
    store.receive_shipment(payload=payload)
    # Error was logged for the new book without the publisher
    assert caplog.record_tuples == [('django', 40, 'Publisher is missing for the book Speak memory')]
    
    assert books_in_store.all().count() == total_unique_titles
    assert books_in_store.aggregate(Sum('stock'))['stock__sum'] == total_items


def test_sell_books(create_everybody):
    publisher, store = create_everybody
    # Add some books to the stock
    payload = [{"Title": "Pnin",
                "Publisher": "Molodaya gvardia",
                "Quantity": 1},
               {"Title": "Lolita",
                "Publisher": "Molodaya gvardia",
                "Quantity": 10}]
    
    total_unique_titles, total_items = util_count_received(store=store,
                                                           payload=payload)
    store.receive_shipment(payload=payload)
    books_in_store = Inventory.objects.filter(store=store)
    assert books_in_store.count() == total_unique_titles
    assert books_in_store.aggregate(Sum('stock'))['stock__sum'] == total_items

    # Sell some books, attempt to oversell Lolitas and sell The Gift which is not in stock.
    payload = [{"Title": "Pnin",
                "Quantity": 1},
               {"Title": "Lolita",
                "Quantity": 500},
               {"Title": "The Gift",
                "Quantity": 500}]
    
    new_stock = util_count_sold(store=store, payload=payload)
    store.sell_books(payload)
    # Set of titles should not change, only the number of individual items 
    assert books_in_store.all().count() == total_unique_titles
    assert books_in_store.aggregate(Sum('stock'))['stock__sum'] == sum(new_stock.values())
    assert [('django', 40, 'Attempt to sell too many items of Lolita. Ignored.')] in caplog.record_tuples 
    assert [('django', 40, 'The Gift is not in stock. Ignored.')] in caplog.record_tuples 
    


def test_selling_book_not_in_stock(create_everybody):
    pass
