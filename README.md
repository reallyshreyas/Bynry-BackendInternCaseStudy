
# Bynry-BackendInternCaseStudy

# PART 1 - CODE REVIEW AND DEBUGGING

Part 1: 
Code Review and Debugging

Solution: 

There are two issues resisting the code which doesn't work as expected in the production
There are two commits mentioned which creates a race condition making it more time to execute.

Case: If the first commit passes but due the server overload it could not pass the second commit, it'll lead to data inconsistency

def create_product():
    data = request.json

    # Create new product object
    product = Product(
        name=data['name'],
        sku=data['sku'],
        price=data['price'],
        warehouse_id=data['warehouse_id']
    )
    db.session.add(product)

    #Flush the session to get the new Product ID's, makes product ID available for next step
    db.session.flush()

    #Create Inventory record using the new product ID
        inventory = Inventory(
        product_id= product.id,
        warehouse_id = data['warehouse_id'],
        quantity=data['initial_quantity']
    )
    db.session.add(inventory)

    #Commit now both Product and Inventory together
    db.session.commit()
    return {"message": "Product created", "product_id": product.id}
