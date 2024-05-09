import redis
import pickle

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)
redis_client.expire('key1', 600)  # 600 seconds = 10 minutes
# CREATE: Store an object in Redis
def store_object(key, obj):
    serialized_obj = pickle.dumps(obj)
    redis_client.set(key, serialized_obj)

# READ: Retrieve an object from Redis
def retrieve_object(key):
    serialized_obj = redis_client.get(key)
    if serialized_obj is not None:
        obj = pickle.loads(serialized_obj)
        return obj
    else:
        return None

# UPDATE: Update an object in Redis
def update_object(key, updated_obj):
    if redis_client.exists(key):
        serialized_obj = pickle.dumps(updated_obj)
        redis_client.set(key, serialized_obj)
    else:
        #store_object(key,updated_obj)
        raise KeyError("Key not found")

# DELETE: Delete an object from Redis
def delete_object(key):
    if redis_client.exists(key):
        redis_client.delete(key)
    else:
        raise KeyError("Key not found")


# Example usage
class MyObject:
    def __init__(self, name):
        self.name = name


def test():
    obj1 = MyObject("Object 1")

    # CREATE: Store the object in Redis
    store_object("obj1", obj1)

    # READ: Retrieve the object from Redis
    retrieved_obj1 = retrieve_object("obj1")
    if retrieved_obj1 is not None:
        print("Retrieved Object 1:", retrieved_obj1.name)

    # UPDATE: Update the object in Redis
    obj1.name = "Updated Object 1"
    update_object("obj1", obj1)

    # READ: Retrieve the updated object from Redis
    retrieved_obj1 = retrieve_object("obj1")
    if retrieved_obj1 is not None:
        print("Updated Object 1:", retrieved_obj1.name)

    # DELETE: Delete the object from Redis
    delete_object("obj1")

    # READ: Attempt to retrieve the deleted object from Redis
    retrieved_obj1 = retrieve_object("obj1")
    if retrieved_obj1 is None:
        print("Object 1 has been deleted")


    # CREATE: Set a string value
    redis_client.set('key1', 'value1')

    # READ: Get the value of a key
    value1 = redis_client.get('key1')
    print("Value1:", value1.decode())

    # UPDATE: Update the value of a key
    redis_client.set('key1', 'new_value')
    value1_updated = redis_client.get('key1')
    print("Updated Value1:", value1_updated.decode())

    # DELETE: Delete a key
    redis_client.delete('key1')
    value1_deleted = redis_client.get('key1')
    if value1_deleted is None:
        print("Key1 has been deleted")
    else:
        print("Key1 still exists")