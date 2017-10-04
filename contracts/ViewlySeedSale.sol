// The MIT License (MIT)
// Copyright (c) 2017 Viewly (https://view.ly)

pragma solidity ^0.4.16;

import "./dappsys/math.sol";
import "./dappsys/token.sol";
import "./dappsys/auth.sol";

/* Viewly seed token sale contract, where buyers send ethers to receive ERC-20
 * VIEW tokens in return. It features:
 * - instant token payback when eth is sent
 * - max funding and max VIEW tokens hard-caps
 * - min funding requirement (else deposits can be reclaimed)
 * - sale start time and duration is set after deploy
 * - sale can be ended anytime after start
 * - token is stopped right after sale ends
 * - deposits can be collected any time after min funding is reached
 *
 * Amount of VIEW tokens send back to buyers decreases linearly: early buyers
 * get bonus tokens over late buyers. Bonus is maximal at the beginning (15%)
 * and gradually lowers as deposits are sent in. It is finally reduced to zero
 * as max funding cap is reached. Token bonus also applies inside a single
 * purchase: even the first buyer gets lower average bonus if sends in more
 * ethers. If first buyer sends in 4000 eth (eth cap), his average bonus will be
 * half of max bonus because his purchase spans from max bonus to 0 bonus (end
 * of sale).
 *
 * The sale always reaches max funding and token caps simultaneously.
 * Average amount of tokens per eth sent will always be the same
 * (and equal to MAX_TOKENS/MAX_FUNDING).
 */
contract ViewlySeedSale is DSAuth, DSMath {

    uint constant public MAX_FUNDING =        4000 ether;  // max funding hard-cap
    uint constant public MIN_FUNDING =        1000 ether;  // min funding requirement
    uint constant public MAX_TOKENS = 10 * 1000000 ether;  // token hard-cap
    uint constant public BONUS =              0.15 ether;  // bonus of tokens early buyers
                                                           // get over last buyers

    DSToken public viewToken;         // VIEW token contract
    address public beneficiary;       // destination to collect eth deposits
    uint public startBlock;           // start block of sale
    uint public endBlock;             // end block of sale

    uint public totalEthDeposited;    // sums of ether raised
    uint public totalTokensBought;    // total tokens issued on sale
    uint public totalEthCollected;    // total eth collected from sale
    uint public totalEthRefunded;     // total eth refunded after a failed sale

    // buyers ether deposits
    mapping (address => uint) public ethDeposits;
    // ether refunds after a failed sale
    mapping (address => uint) public ethRefunds;

    enum State {
        Pending,
        Running,
        Succeeded,
        Failed
    }
    State public state = State.Pending;

    event LogBuy(
        address buyer,
        uint ethDeposit,
        uint tokensBought
    );

    event LogRefund(
        address buyer,
        uint ethRefund
    );

    event LogStartSale(
        uint startBlock,
        uint endBlock
    );

    event LogEndSale(
        bool success,
        uint totalEthDeposited,
        uint totalTokensBought
    );

    event LogExtendSale(
        uint blocks
    );

    event LogCollectEth(
        uint ethCollected,
        uint totalEthDeposited
    );

    // require given state of sale
    modifier saleIn(State state_) { require(state_ == state); _; }

    // check current block is inside closed interval [startBlock, endBlock]
    modifier inRunningBlock() {
        require(block.number >= startBlock);
        require(block.number < endBlock);
        _;
    }
    // check sender has sent some ethers
    modifier ethSent() { require(msg.value > 0); _; }


    // PUBLIC //

    function ViewlySeedSale(DSToken viewToken_, address beneficiary_) {
        viewToken = viewToken_;
        beneficiary = beneficiary_;
    }

    function() payable {
        buyTokens();
    }

    function buyTokens() saleIn(State.Running) inRunningBlock ethSent payable {
        uint tokensBought = calcTokensForPurchase(msg.value, totalEthDeposited);
        ethDeposits[msg.sender] = add(msg.value, ethDeposits[msg.sender]);
        totalEthDeposited = add(msg.value, totalEthDeposited);
        totalTokensBought = add(tokensBought, totalTokensBought);

        require(totalEthDeposited <= MAX_FUNDING);
        require(totalTokensBought <= MAX_TOKENS);

        viewToken.mint(msg.sender, tokensBought);

        LogBuy(msg.sender, msg.value, tokensBought);
    }

    function claimRefund() saleIn(State.Failed) {
      require(ethDeposits[msg.sender] > 0);
      require(ethRefunds[msg.sender] == 0);

      uint ethRefund = ethDeposits[msg.sender];
      ethRefunds[msg.sender] = ethRefund;
      totalEthRefunded = add(ethRefund, totalEthRefunded);
      msg.sender.transfer(ethRefund);

      LogRefund(msg.sender, ethRefund);
    }


    // AUTH REQUIRED //

    function startSale(uint duration, uint blockOffset) auth saleIn(State.Pending) {
        require(duration > 0);
        require(blockOffset >= 0);

        startBlock = add(block.number, blockOffset);
        endBlock   = add(startBlock, duration);
        state      = State.Running;

        LogStartSale(startBlock, endBlock);
    }

    function endSale() auth saleIn(State.Running) {
        if (totalEthDeposited >= MIN_FUNDING)
          state = State.Succeeded;
        else
          state = State.Failed;

        viewToken.stop();
        LogEndSale(state == State.Succeeded, totalEthDeposited, totalTokensBought);
    }

    function extendSale(uint blocks) auth saleIn(State.Running) {
        require(blocks > 0);

        endBlock = add(endBlock, blocks);
        LogExtendSale(blocks);
    }

    function collectEth() auth {
        require(totalEthDeposited >= MIN_FUNDING);
        require(this.balance > 0);

        uint ethToCollect = this.balance;
        totalEthCollected = add(totalEthCollected, ethToCollect);
        beneficiary.transfer(ethToCollect);
        LogCollectEth(ethToCollect, totalEthDeposited);
    }


    // PRIVATE //

    uint constant averageTokensPerEth = wdiv(MAX_TOKENS, MAX_FUNDING);
    uint constant endingTokensPerEth = wdiv(2 * averageTokensPerEth, 2 ether + BONUS);

    // calculate number of tokens buyer get when sending 'ethSent' ethers
    // after 'ethDepostiedSoFar` already reeived in the sale
    function calcTokensForPurchase(uint ethSent, uint ethDepositedSoFar)
        private view
        returns (uint tokens)
    {
        uint tokensPerEthAtStart = calcTokensPerEth(ethDepositedSoFar);
        uint tokensPerEthAtEnd = calcTokensPerEth(add(ethDepositedSoFar, ethSent));
        uint averageTokensPerEth = add(tokensPerEthAtStart, tokensPerEthAtEnd) / 2;

        // = ethSent * averageTokensPerEthInThisPurchase
        return wmul(ethSent, averageTokensPerEth);
    }

    // return tokensPerEth for 'nthEther' of total contribution (MAX_FUNDING)
    function calcTokensPerEth(uint nthEther)
        private view
        returns (uint)
    {
        uint shareOfSale = wdiv(nthEther, MAX_FUNDING);
        uint shareOfBonus = sub(1 ether, shareOfSale);
        uint actualBonus = wmul(shareOfBonus, BONUS);

        // = endingTokensPerEth * (1 + shareOfBonus * BONUS)
        return wmul(endingTokensPerEth, add(1 ether, actualBonus));
    }
}
