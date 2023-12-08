# import all the necessary libraries and modules

import hashlib
import json
import sys
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request


def encrypt(message, multiple):
    return "".join(chr((ord(char) * multiple) % 256) for char in str(message))


def decrypt(message, multiple):
    inverse = 0
    for i in range(256):
        if (multiple * i) % 256 == 1:
            inverse = i
            break
    return "".join(chr((ord(char) * inverse) % 256) for char in str(message))


# noinspection PyMethodMayBeStatic
class Blockchain(object):
    # The __init__() function is the constructor for the class. Here, you
    # store the entire blockchain as a list. Because every blockchain has a
    # genesis block, you need to initialize the genesis block with the hash
    # of the previous block, and in this example, we simply used a fixed
    # string called “genesis_block” to obtain its hash. Once the hash of the
    # previous block is found, we need to find the nonce for the block using
    # the method named proof_of_work() (which we will define in the
    # next section).

    def __init__(self):
        self.nodes = set()

        # stores all the blocks in the entire blockchain
        self.chain = []

        # temporarily stores the transactions for the current block
        self.current_transactions = []

        self.difficulty = 1

        self.target_time = 5

        self.multiple = 7

        # create the genesis block with a specific fixed hash
        # of previous block genesis block starts with index 0
        hash, nonce, time_spent = self.proof_of_work(0, 0, [])
        self.append_block(hash, nonce, time_spent, 0)

    def adjust_difficulty(self):
        mean_time = sum(block['time_spent'] for block in self.chain[-4:]) / min(4, len(self.chain))
        self.difficulty *= (mean_time == self.target_time and 1 or mean_time > self.target_time and 0.9 or 1.2)
        if self.difficulty < 1:
            self.difficulty = 1

    def add_node(self, address):
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)
        print(parsed_url.netloc)

    # determine if a given blockchain is valid
    def valid_chain(self, chain):
        last_block = chain[0]  # the genesis block
        current_index = 1  # starts with the second block
        while current_index < len(chain):
            block = chain[current_index]
            if block['previous_hash'] != last_block['hash']:
                return False

            # check for valid nonce
            if block['hash'] != self.calculate_hash(current_index,
                                                    block['previous_hash'],
                                                    block['transactions'],
                                                    block['nonce']):
                return False

            # move on to the next block on the chain
            last_block = block
            current_index += 1

        # the chain is valid
        return True

    def update_blockchain(self):
        # get the surrounding nodes that has been registered
        neighbours = self.nodes
        new_chain = None
        # for simplicity, look for chains longer than ours
        max_length = len(self.chain)
        # grab and verify the chains from all the nodes in our
        # network
        for node in neighbours:
            # get the blockchain from the other nodes
            response = requests.get(f'http://{node}/blockchain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']
                # check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False

    # The proof_of_work() method (detailed next) will return a nonce that will result in a
    # hash that matches the difficulty target when the content of the current block is hashed.
    # For simplicity, we are fixing the difficulty_target to a hash result that starts with four zeros (“0000”).

    # The proof_of_work() function first starts with zero for the nonce and check if the
    # nonce together with the content of the block produces a hash that matches the difficulty
    # target. If not, it increments the nonce by one and then try again until it finds the correct nonce.

    # use PoW to find the nonce for the current block
    def proof_of_work(self, index, previous_hash, transactions):
        # try with nonce = 0
        nonce = 0
        hash = ''
        start_time = time()
        # try hashing the nonce together with the hash of the
        # previous block until it is valid
        while self.meets_difficulty(hash) is False:
            nonce += 1
            hash = self.calculate_hash(index, previous_hash, transactions, nonce)

        return hash, nonce, time() - start_time

    # The next method, valid_proof(), hashes the content of a block and check to see if
    # the block’s hash meets the difficulty target:

    def meets_difficulty(self, hash):
        # check if the hash meets the difficulty target
        return hash.startswith('0' * int(self.difficulty))

    def calculate_hash(self, index, previous_block, transactions, nonce):
        return hashlib.sha256(f'{index}{previous_block}{transactions}{nonce}'.encode()).hexdigest()

    # creates a new block and adds it to the blockchain
    def append_block(self, hash, nonce, time_spent, previous_hash=None):

        block = {
            'hash': hash,
            'index': len(self.chain),
            'timestamp': time(),
            'transactions': self.current_transactions,
            'nonce': nonce,
            'time_spent': time_spent,
            'previous_hash': previous_hash
        }

        # reset the current list of transactions
        self.current_transactions = []

        # add the new block to the blockchain
        self.chain.append(block)

        self.adjust_difficulty()

        return block

    def add_transaction(self, sender, recipient, amount):

        self.current_transactions.append({
            'amount': encrypt(amount, self.multiple),
            'recipient': recipient,
            'sender': sender,
        })

        return self.last_block['index'] + 1

    @property
    def last_block(self):
        # returns the last block in the blockchain
        return self.chain[-1]

    @property
    def last_hash(self):
        # returns the last block in the blockchain
        return self.last_block['hash']


app = Flask(__name__)
# generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', "")
# instantiate the Blockchain
blockchain = Blockchain()


# return the entire blockchain
@app.route('/blockchain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }

    return jsonify(response), 200


@app.route('/mine', methods=['GET'])
def mine_block():
    blockchain.add_transaction(sender="0", recipient=node_identifier, amount=1)

    # obtain the hash of last block in the blockchain
    last_block_hash = blockchain.last_hash

    # using PoW, get the nonce for the new block to be added to the blockchain
    index = len(blockchain.chain)
    hash, nonce, time_spent = blockchain.proof_of_work(index, last_block_hash, blockchain.current_transactions)

    # add the new block to the blockchain using the last block
    # hash and the current nonce
    block = blockchain.append_block(hash, nonce, time_spent, last_block_hash)

    response = {
        'message': "New Block Mined",
        'hash': hash,
        'index': index,
        'previous_hash': last_block_hash,
        'nonce': nonce,
        'time_spent': time_spent,
        'transactions': block['transactions'],
    }
    return jsonify(response), 200


@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    # get the value passed in from the client
    values = request.get_json()

    # check that the required fields are in the POST'ed data
    required_fields = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required_fields):
        return 'Missing fields', 400

    # create a new transaction
    index = blockchain.add_transaction(
        values['sender'],
        values['recipient'],
        values['amount']
    )

    response = {'message': f'Transaction will be added to Block {index}'}

    return jsonify(response), 201


@app.route('/nodes/add_nodes', methods=['POST'])
def add_nodes():
    # get the nodes passed in from the client
    values = json.loads(request.data, strict=False)
    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Missing node(s) info", 400

    for node in nodes:
        blockchain.add_node(node)
        response = {
            'message': 'New nodes added',
            'nodes': list(blockchain.nodes),
        }
        return jsonify(response), 201


@app.route('/nodes/sync', methods=['GET'])
def sync():
    updated = blockchain.update_blockchain()
    if updated:
        response = {
            'message':
                'The blockchain has been updated to the latest',
            'blockchain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our blockchain is the latest',
            'blockchain': blockchain.chain
        }

    return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(sys.argv[1]))
