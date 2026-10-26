// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// Feature: maharashtra-tourist-safety
// Implements: Requirements 1.3, 1.4, 1.6, 4.6, 6.3, 8.7, 11.1, 11.5

/**
 * @title TouristSafety
 * @notice Blockchain-based digital tourist identity registry for Maharashtra.
 *         Records are immutable after creation; only the owner may expire a record.
 */
contract TouristSafety {
    // -------------------------------------------------------------------------
    // Types
    // -------------------------------------------------------------------------

    enum TouristStatus { ACTIVE, EXPIRED }

    struct TouristRecord {
        bytes32 idHash;        // SHA-256 hash of the tourist's identity document
        uint256 visitStart;    // Unix timestamp — start of visit
        uint256 visitEnd;      // Unix timestamp — end of visit
        TouristStatus status;  // ACTIVE or EXPIRED
        bool exists;           // guard flag to distinguish uninitialised entries
    }

    /// @dev Represents an on-chain SOS event (Requirement 6.3)
    struct SosEvent {
        bytes32 eventId;
        uint256 tokenId;
        int256  lat;
        int256  lng;
        uint256 timestamp;
        bool    resolved;
        address officerId;
    }

    /// @dev Records a tourist entering a geo-fence zone (Requirement 4.6)
    struct ZoneEntry {
        uint256 tokenId;
        string  zoneName;
        uint256 timestamp;
    }

    /// @dev Represents a resolved incident anchored on-chain (Requirement 8.7)
    struct Incident {
        bytes32 incidentId;
        uint256 tokenId;
        uint256 resolvedAt;
        address officerId;
    }

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    address public owner;

    /// @dev Auto-incrementing token counter; starts at 1 so tokenId 0 is invalid
    uint256 private _nextTokenId;

    /// @dev Primary storage: tokenId → TouristRecord
    mapping(uint256 => TouristRecord) private _records;

    /// @dev SOS event storage: eventId → SosEvent
    mapping(bytes32 => SosEvent) private _sosEvents;

    /// @dev Incident storage: incidentId → Incident
    mapping(bytes32 => Incident) private _incidents;

    // -------------------------------------------------------------------------
    // Events
    // -------------------------------------------------------------------------

    /// @notice Emitted when a new tourist is registered on-chain
    event TouristRegistered(
        uint256 indexed tokenId,
        bytes32 indexed idHash,
        uint256 visitStart,
        uint256 visitEnd
    );

    /// @notice Emitted when a tourist record is marked as expired
    event TouristExpired(uint256 indexed tokenId);

    /// @notice Emitted when an SOS event is recorded on-chain (Requirement 6.3)
    event SosCreated(
        bytes32 indexed eventId,
        uint256 indexed tokenId,
        int256  lat,
        int256  lng,
        uint256 timestamp
    );

    /// @notice Emitted when an SOS event is resolved (Requirement 6.3)
    event SosResolved(bytes32 indexed eventId, address indexed officerId);

    /// @notice Emitted when a tourist enters a restricted zone (Requirement 4.6)
    event RestrictedZoneEntered(
        uint256 indexed tokenId,
        string  zoneName,
        uint256 timestamp
    );

    /// @notice Emitted when an incident is resolved on-chain (Requirement 8.7)
    event IncidentResolved(
        bytes32 indexed incidentId,
        uint256 indexed tokenId,
        address indexed officerId,
        uint256 resolvedAt
    );

    // -------------------------------------------------------------------------
    // Modifiers
    // -------------------------------------------------------------------------

    modifier onlyOwner() {
        require(msg.sender == owner, "TouristSafety: caller is not the owner");
        _;
    }

    modifier recordExists(uint256 tokenId) {
        require(_records[tokenId].exists, "TouristSafety: record does not exist");
        _;
    }

    // -------------------------------------------------------------------------
    // Constructor
    // -------------------------------------------------------------------------

    constructor() {
        owner = msg.sender;
        _nextTokenId = 1;
    }

    // -------------------------------------------------------------------------
    // External functions
    // -------------------------------------------------------------------------

    /**
     * @notice Register a tourist and anchor their identity on-chain.
     * @param idHash     SHA-256 hash of the tourist's Aadhaar or passport number.
     * @param visitStart Unix timestamp for the start of the visit.
     * @param visitEnd   Unix timestamp for the end of the visit.
     * @return tokenId   The unique on-chain identifier for this tourist record.
     *
     * Requirements:
     *   - idHash must be non-zero.
     *   - visitEnd must be strictly after visitStart.
     *   - Once created the record is immutable (Requirement 1.6, 11.3).
     */
    function registerTourist(
        bytes32 idHash,
        uint256 visitStart,
        uint256 visitEnd
    ) external returns (uint256 tokenId) {
        require(idHash != bytes32(0), "TouristSafety: idHash cannot be zero");
        require(visitEnd > visitStart, "TouristSafety: visitEnd must be after visitStart");

        tokenId = _nextTokenId;
        _nextTokenId++;

        _records[tokenId] = TouristRecord({
            idHash: idHash,
            visitStart: visitStart,
            visitEnd: visitEnd,
            status: TouristStatus.ACTIVE,
            exists: true
        });

        emit TouristRegistered(tokenId, idHash, visitStart, visitEnd);
    }

    /**
     * @notice Mark a tourist record as expired.
     * @param tokenId The token ID of the tourist record to expire.
     *
     * Requirements:
     *   - Caller must be the contract owner (Requirement 1.4).
     *   - Record must exist.
     *   - Record must currently be ACTIVE (idempotent guard).
     */
    function expireTourist(uint256 tokenId)
        external
        onlyOwner
        recordExists(tokenId)
    {
        require(
            _records[tokenId].status == TouristStatus.ACTIVE,
            "TouristSafety: record is already expired"
        );

        _records[tokenId].status = TouristStatus.EXPIRED;

        emit TouristExpired(tokenId);
    }

    /**
     * @notice Record an SOS event on-chain.
     * @param tokenId   The tourist's token ID.
     * @param lat       Latitude in micro-degrees (e.g. 18.975 → 18975000).
     * @param lng       Longitude in micro-degrees.
     * @param timestamp Unix timestamp of the SOS trigger.
     * @return eventId  keccak256(tokenId, timestamp, lat, lng)
     *
     * Requirements (6.3, 11.1):
     *   - Record must exist for tokenId.
     *   - eventId must be unique (not already recorded).
     */
    function recordSosEvent(
        uint256 tokenId,
        int256  lat,
        int256  lng,
        uint256 timestamp
    ) external recordExists(tokenId) returns (bytes32 eventId) {
        eventId = keccak256(abi.encodePacked(tokenId, timestamp, lat, lng));
        require(_sosEvents[eventId].timestamp == 0, "TouristSafety: SOS event already recorded");

        _sosEvents[eventId] = SosEvent({
            eventId:   eventId,
            tokenId:   tokenId,
            lat:       lat,
            lng:       lng,
            timestamp: timestamp,
            resolved:  false,
            officerId: address(0)
        });

        emit SosCreated(eventId, tokenId, lat, lng, timestamp);
    }

    /**
     * @notice Mark an SOS event as resolved.
     * @param eventId   The SOS event ID returned by recordSosEvent.
     * @param officerId Address of the responding officer.
     *
     * Requirements (6.3):
     *   - Event must exist and not already be resolved.
     */
    function resolveSosEvent(bytes32 eventId, address officerId) external {
        SosEvent storage ev = _sosEvents[eventId];
        require(ev.timestamp != 0, "TouristSafety: SOS event does not exist");
        require(!ev.resolved, "TouristSafety: SOS event already resolved");

        ev.resolved  = true;
        ev.officerId = officerId;

        emit SosResolved(eventId, officerId);
    }

    /**
     * @notice Record a tourist entering a geo-fence zone on-chain.
     * @param tokenId   The tourist's token ID.
     * @param zoneName  Human-readable zone name (e.g. "Tadoba Tiger Reserve").
     * @param timestamp Unix timestamp of zone entry.
     *
     * Requirements (4.6, 11.1):
     *   - Record must exist for tokenId.
     */
    function recordZoneEntry(
        uint256        tokenId,
        string calldata zoneName,
        uint256        timestamp
    ) external recordExists(tokenId) {
        emit RestrictedZoneEntered(tokenId, zoneName, timestamp);
    }

    /**
     * @notice Resolve an incident and anchor the resolution on-chain.
     * @param incidentId keccak256(tokenId, createdAt) — generated off-chain.
     * @param officerId  Address of the resolving officer.
     * @param timestamp  Unix timestamp of resolution.
     *
     * Requirements (8.7):
     *   - incidentId must not already be resolved.
     */
    function resolveIncident(
        bytes32 incidentId,
        address officerId,
        uint256 timestamp
    ) external {
        require(_incidents[incidentId].resolvedAt == 0, "TouristSafety: incident already resolved");

        // Derive tokenId from the incidentId mapping; store with provided data.
        // The tokenId is embedded in the incidentId by the caller (off-chain).
        // We store 0 as tokenId here since it is not passed; callers should use
        // the off-chain record for the full incident details.
        _incidents[incidentId] = Incident({
            incidentId: incidentId,
            tokenId:    0,
            resolvedAt: timestamp,
            officerId:  officerId
        });

        emit IncidentResolved(incidentId, 0, officerId, timestamp);
    }

    // -------------------------------------------------------------------------
    // View functions
    // -------------------------------------------------------------------------

    /**
     * @notice Retrieve a tourist record by token ID.
     * @param tokenId The token ID to look up.
     * @return idHash     The stored identity hash.
     * @return visitStart The visit start timestamp.
     * @return visitEnd   The visit end timestamp.
     * @return status     The current status (0 = ACTIVE, 1 = EXPIRED).
     */
    function getTouristRecord(uint256 tokenId)
        external
        view
        recordExists(tokenId)
        returns (
            bytes32 idHash,
            uint256 visitStart,
            uint256 visitEnd,
            TouristStatus status
        )
    {
        TouristRecord storage rec = _records[tokenId];
        return (rec.idHash, rec.visitStart, rec.visitEnd, rec.status);
    }

    /**
     * @notice Check whether a token ID has an associated record.
     * @param tokenId The token ID to check.
     * @return True if the record exists, false otherwise.
     */
    function recordExistsFor(uint256 tokenId) external view returns (bool) {
        return _records[tokenId].exists;
    }

    /**
     * @notice Returns the next token ID that will be assigned on the next registration.
     */
    function nextTokenId() external view returns (uint256) {
        return _nextTokenId;
    }
}
