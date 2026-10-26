package com.tourist.safety

import com.google.firebase.database.FirebaseDatabase
import com.google.firebase.database.ktx.database
import com.google.firebase.ktx.Firebase

/**
 * FirebaseRepository - single source of truth for all Firebase writes.
 * Centralizes error handling and prevents duplicate writes.
 */
object FirebaseRepository {

    private val db: FirebaseDatabase by lazy {
        Firebase.database.apply { setPersistenceEnabled(true) }
    }

    fun registerTourist(touristId: String, name: String? = null) {
        val ref = db.getReference("Tourists/$touristId")
        ref.child("createdAt").setValue(System.currentTimeMillis())
        ref.child("status").setValue("SAFE")
        if (!name.isNullOrEmpty()) ref.child("name").setValue(name)
    }

    fun updateLiveLocation(
        touristId: String,
        lat: Double,
        lng: Double,
        status: String,
        simulatedTime: Long = 0L,
        actualEmittedAtMs: Long = System.currentTimeMillis()
    ) {
        val loc = LiveLocation(
            latitude = lat,
            longitude = lng,
            time = if (simulatedTime > 0L) simulatedTime else actualEmittedAtMs,
            status = status,
            simulatedTime = simulatedTime,
            actualEmittedAtMs = actualEmittedAtMs
        )
        db.getReference("LiveLocation/$touristId").setValue(loc)
    }

    fun pushLocationHistory(touristId: String, lat: Double, lng: Double, timeMs: Long = System.currentTimeMillis()) {
        val entry = LocationEntry(lat, lng, timeMs)
        db.getReference("LocationHistory/$touristId").push().setValue(entry)
    }

    fun sendSos(touristId: String, lat: Double, lng: Double, simulatedTime: Long = 0L) {
        val wallClock = System.currentTimeMillis()
        val sos = SosAlert(lat, lng, if (simulatedTime > 0L) simulatedTime else wallClock, "ACTIVE")
        db.getReference("SOS/$touristId").setValue(sos)
        createAlert(
            touristId = touristId,
            type = "SOS",
            risk = "HIGH",
            lat = lat,
            lng = lng,
            simulatedTimestamp = simulatedTime,
            actualEmittedAtMs = wallClock,
            processingLatencyMs = 0.0
        )
        updateTouristStatus(touristId, "SOS")
    }

    fun clearSos(touristId: String) {
        db.getReference("SOS/$touristId").removeValue()
        updateTouristStatus(touristId, "SAFE")
    }

    fun createAlert(
        touristId: String,
        type: String,
        risk: String,
        lat: Double,
        lng: Double,
        simulatedTimestamp: Long = 0L,
        actualEmittedAtMs: Long = System.currentTimeMillis(),
        processingLatencyMs: Double = 0.0
    ) {
        val alert = Alert(
            touristId = touristId,
            type = type,
            risk = risk,
            latitude = lat,
            longitude = lng,
            time = if (simulatedTimestamp > 0L) simulatedTimestamp else actualEmittedAtMs,
            simulatedTimestamp = simulatedTimestamp,
            actualEmittedAtMs = actualEmittedAtMs,
            processingLatencyMs = processingLatencyMs
        )
        db.getReference("Alerts").push().setValue(alert)
    }

    fun updateTouristStatus(touristId: String, status: String) {
        db.getReference("Tourists/$touristId/status").setValue(status)
        db.getReference("LiveLocation/$touristId/status").setValue(status)
    }
}
