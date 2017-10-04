import pytest

from pytest import approx
from web3.contract import Contract
from eth_utils import to_wei

from ethereum.tester import TransactionFailed
from populus.chain.base import BaseChain


MAX_TOKENS      = to_wei(10000000, 'ether')
MAX_FUNDING     = to_wei(4000, 'ether')
MIN_FUNDING     = to_wei(1000, 'ether')
DURATION        = 10
BLOCK_OFFSET    = 2

def deploy_contract(chain: BaseChain, contract_name: str, args=[]) -> Contract:
    # deploy contract on chain with coinbase and optional init args
    factory = chain.get_contract_factory(contract_name)
    deploy_tx_hash = factory.deploy(args=args)
    contract_address = chain.wait.for_contract_address(deploy_tx_hash)
    return factory(address=contract_address)

def send_eth_to_sale(chain, sale, user, eth_to_send):
    return chain.web3.eth.sendTransaction({
        'from': user,
        'to': sale.address,
        'value': eth_to_send,
        'gas': 250000,
    })

def assert_last_buy_event(sale, buyer, eth_sent, tokens_bought):
    event = sale.pastEvents('LogBuy').get()[-1]['args']
    assert event['buyer'] == buyer
    assert event['ethDeposit'] == eth_sent
    assert event['tokensBought'] == approx(tokens_bought)

def assert_last_refund_event(sale, buyer, eth_refund):
    event = sale.pastEvents('LogRefund').get()[-1]['args']
    assert event['buyer'] == buyer
    assert event['ethRefund'] == eth_refund

def assert_last_collect_eth_event(sale, collected, total_eth):
    event = sale.pastEvents('LogCollectEth').get()[-1]['args']
    assert event['ethCollected'] == collected
    assert event['totalEthDeposited'] == total_eth

def assert_last_extend_sale_event(sale, blocks):
    event = sale.pastEvents('LogExtendSale').get()[-1]['args']
    assert event['blocks'] == blocks

def assert_end_sale_event(sale, success, total_eth, total_tokens=None):
    event = sale.pastEvents('LogEndSale').get()[0]['args']
    assert event['success'] == success
    assert event['totalEthDeposited'] == total_eth
    if total_tokens:
        assert event['totalTokensBought'] == approx(total_tokens)
def assert_last_collect_eth_event(sale, collected, total_eth):
    event = sale.pastEvents('LogCollectEth').get()[-1]['args']
    assert event['ethCollected'] == collected
    assert event['totalEthDeposited'] == total_eth

@pytest.fixture()
def token(chain: BaseChain) -> Contract:
    """ A VIEW token contract. """
    return deploy_contract(chain, 'DSToken', args=['VIEW'])

@pytest.fixture()
def sale(chain: BaseChain, token: Contract, beneficiary) -> Contract:
    """ A blank ViewlySeedSale contract. """
    args = [token.address, beneficiary]
    seed_sale = deploy_contract(chain, 'ViewlySeedSale', args=args)
    token.transact().setOwner(seed_sale.address)
    return seed_sale

@pytest.fixture()
def running_sale(chain: BaseChain, token: Contract, sale) -> Contract:
    """ A running ViewlySeedSale contract. """
    sale.transact().startSale(DURATION, BLOCK_OFFSET)
    chain.wait.for_block(sale.call().startBlock())
    return sale

@pytest.fixture
def owner(accounts) -> str:
    return accounts[0]

@pytest.fixture
def customer(accounts) -> str:
    return accounts[1]

@pytest.fixture
def customer2(accounts) -> str:
    return accounts[2]

@pytest.fixture
def beneficiary(accounts) -> str:
    return accounts[3]


# --------
# TESTS
# --------

def test_init(chain, token, beneficiary):
    sale = deploy_contract(chain, 'ViewlySeedSale', args=[token.address, beneficiary])

    assert sale.call().viewToken() == token.address
    assert sale.call().beneficiary() == beneficiary

def test_start_sale(web3, sale):
    sale.transact().startSale(DURATION, BLOCK_OFFSET)
    expected_start_block = web3.eth.blockNumber + BLOCK_OFFSET
    expected_end_block = web3.eth.blockNumber + BLOCK_OFFSET + DURATION

    assert sale.call().state() == 1
    assert sale.call().MAX_FUNDING() == MAX_FUNDING
    assert sale.call().MAX_TOKENS() == MAX_TOKENS
    assert sale.call().startBlock() == expected_start_block
    assert sale.call().endBlock() == expected_end_block

    start_event = sale.pastEvents('LogStartSale').get()[0]['args']
    assert start_event['startBlock'] == expected_start_block
    assert start_event['endBlock'] == expected_end_block

def test_end_sale_succeeded(chain: BaseChain, token, running_sale, customer):
    sale = running_sale
    send_eth_to_sale(chain, sale, customer, MAX_FUNDING)

    sale.transact().endSale()

    assert sale.call().state() == 2
    assert_end_sale_event(sale, True, MAX_FUNDING, approx(MAX_TOKENS))
    assert token.call().stopped()

def test_end_sale_failed_and_refund(chain: BaseChain, token, running_sale, customer):
    sale = running_sale
    eth_sent = MIN_FUNDING - to_wei(1, 'ether')
    send_eth_to_sale(chain, sale, customer, eth_sent)
    sale.transact().endSale()

    # sale should be failed
    assert sale.call().state() == 3
    assert_end_sale_event(sale, False, eth_sent)

    # customer claims a refund
    start_balance = chain.web3.eth.getBalance(customer)
    sale.transact({"from": customer}).claimRefund()
    end_balance = chain.web3.eth.getBalance(customer)

    assert (end_balance - start_balance) == approx(eth_sent)
    assert sale.call().totalEthRefunded() == eth_sent
    assert sale.call().ethRefunds(customer) == eth_sent
    assert chain.web3.eth.getBalance(sale.address) == 0
    assert_last_refund_event(sale, customer, eth_sent)

    # if customer retries to claim a refund it should fail
    with pytest.raises(TransactionFailed):
        sale.transact({"from": customer}).claimRefund()


def test_collect_eth(chain: BaseChain, running_sale, customer, beneficiary):
    sale = running_sale
    initial_balance = chain.web3.eth.getBalance(beneficiary)

    # buy some token on sale
    send_eth_to_sale(chain, sale, customer, MIN_FUNDING - to_wei(2, 'ether'))

    # ETH collection should fail before min funding cap is reached
    with pytest.raises(TransactionFailed):
        sale.transact().collectEth()

    # buy more tokens on sale up to min funding cap
    send_eth_to_sale(chain, sale, customer, to_wei(2, 'ether'))

    # collect deposited eth before end of sale
    sale.transact().collectEth()
    balance_change = chain.web3.eth.getBalance(beneficiary) - initial_balance
    assert balance_change == approx(MIN_FUNDING)
    assert chain.web3.eth.getBalance(sale.address) == 0
    assert_last_collect_eth_event(sale, MIN_FUNDING, MIN_FUNDING)

    # buy some more, sale still open
    send_eth_to_sale(chain, sale, customer, to_wei(30, 'ether'))
    assert chain.web3.eth.getBalance(sale.address) == to_wei(30, 'ether')
    assert sale.call().totalEthDeposited() == MIN_FUNDING + to_wei(30, 'ether')

def test_buy(chain, web3, token, sale, customer):
    sale.transact().startSale(DURATION, 0)

    eth_sent = MAX_FUNDING
    expected_tokens = MAX_TOKENS
    send_eth_to_sale(chain, sale, customer, eth_sent)

    # sale contract should save eth deposit and update totals
    assert sale.call().ethDeposits(customer) == eth_sent
    assert web3.eth.getBalance(sale.address) == eth_sent
    assert sale.call().totalEthDeposited() == eth_sent

    # token supply should increase
    assert token.call().totalSupply() == approx(expected_tokens)
    # customer should receive expected tokens
    assert token.call().balanceOf(customer) == approx(expected_tokens)

    assert_last_buy_event(sale, customer, MAX_FUNDING, MAX_TOKENS)

def test_buy_multiple_times_with_bonuses(chain: BaseChain, running_sale, customer):
    sale = running_sale
    half_eth_cap = to_wei(2000, 'ether')

    send_eth_to_sale(chain, sale, customer, half_eth_cap)
    assert_last_buy_event(sale, customer, half_eth_cap, to_wei(5174418.605, 'ether'))

    send_eth_to_sale(chain, sale, customer, half_eth_cap)
    assert_last_buy_event(sale, customer, half_eth_cap, to_wei(4825581.395, 'ether'))

    assert sale.call().totalEthDeposited() == MAX_FUNDING
    assert sale.call().totalTokensBought() == approx(MAX_TOKENS)

def test_buy_multiple_in_diverse_amounts(chain: BaseChain, running_sale, customer):
    sale = running_sale

    send_eth_to_sale(chain, sale, customer, to_wei(111, 'milli'))
    assert_last_buy_event(sale, customer, to_wei(111, 'milli'), to_wei(296.8599279, 'ether'))

    send_eth_to_sale(chain, sale, customer, to_wei(2322, 'ether'))
    assert_last_buy_event(sale, customer, to_wei(2322, 'ether'), to_wei(5974875.023, 'ether'))

    send_eth_to_sale(chain, sale, customer, to_wei(45, 'ether'))
    assert_last_buy_event(sale, customer, to_wei(45, 'ether'), to_wei(111147.6022, 'ether'))

    send_eth_to_sale(chain, sale, customer, to_wei(1632889, 'milli'))
    assert_last_buy_event(sale, customer, to_wei(1632889, 'milli'), to_wei(3913680.515, 'ether'))

    assert sale.call().totalEthDeposited() == MAX_FUNDING
    assert sale.call().totalTokensBought() == approx(MAX_TOKENS)

def test_extend_sale(chain: BaseChain, token, running_sale, customer):
    sale = running_sale

    # buying something on end block should not succeed
    chain.wait.for_block(sale.call().endBlock())
    with pytest.raises(TransactionFailed):
        send_eth_to_sale(chain, sale, customer, to_wei(1, 'ether'))

    # extend sale for few more blocks
    initial_end_block = sale.call().endBlock()
    sale.transact().extendSale(10)
    assert sale.call().endBlock() == (initial_end_block + 10)
    assert_last_extend_sale_event(sale, 10)

    # retry token purchase
    send_eth_to_sale(chain, sale, customer, to_wei(1, 'ether'))
    assert token.call().balanceOf(customer) > 0
    assert chain.web3.eth.getBalance(sale.address) == to_wei(1, 'ether')
