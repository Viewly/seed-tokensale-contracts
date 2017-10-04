![](https://i.imgur.com/ekvJd60.png)

*Viewly is building a decentralized video platform without ads.*

Learn more at https://view.ly


# Viewly Pre-ICO Token Sale (Community Seed Token Sale)

We have built a single-purpose secure smart contract for Viewly pre-ICO token
sale. It can run a crowdsale event on Ethereum blockchain, accepting ethers and
returing ERC20 VIEW tokens.

The sale contract has the following characteristics:

## Instant token payback

Tokens are returned instantly, in the same transaction as ethers are sent in by
the buyer. Tokens are frozen after sale completes (and will be made liquid after
the main ICO).

## Token price and BONUS

Token sale contract features a token bonus that rewards early contributors. The
bonus starts at 15% at the beginning of sale. As more funds are sent in, bonus
gradually decreases and reduces to 0 when maximum funding cap is reached.

Therefore the last token sold will be 15% more expensive than the first token
sold at the sale:
* VIEW price at the start (max bonus): 0.000374 ETH
* VIEW price at the end (zero bonus): 0.000430 ETH
* Average VIEW price (when cap reached): 0.000400 ETH

## Maximum funding and tokens cap

Maximum funding cap is hard-coded at 4000 ETH.

Token cap is hard-coded at 10.000.000 VIEW, representing 10% of total supply.

If reached, both caps are done so simultanously.

## Minimum funding requirement

Minimum funding requirement is hard-coded at 1000 ETH.

This a safety mechanism for buyers' protection. If the minimum isn't reached,
the funds remain locked in the contract. After the sale ends, buyer can
retrieve original ETH deposit by calling claimRefund function, which instantly
returns ETH.

## Flexible sale duration

Sale start offset and duration are set after contract is deployed by calling
startSale (they are based on block number). Sale can be extended. Sale can be
ended anytime after the start.

## Collection and beneficiary

Beneficiary address is where the deposited ETH will be collected to. It is set
at deploy time and cannot be changed after that. ETH collection can be done at
any time and multiple times, but only after the sale reaches minimum funding
requirement.

## Design goals

* Use of Ethereum/Solidity best practices
* Separation of concerns: token sale, token and auth logic are implemented
  separate contracts
* Testable: aim of 100% code coverage by automated test suite (Python)
* Logging: all actions outcomes are logged as public events
* Building on foundation: Using 
  [Dappsys](https://dappsys.readthedocs.io/en/latest/) framework's building
  blocks for common functionality like safe math, ERC-20 token and multisig.
