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

    fun updateLiveLocation(touristId: String, lat: Double, lng: Double, status: String) {
        val loc = LiveLocation(lat, lng, System.currentTimeMillis(), status)
        db.getReference("LiveLocation/$touristId").setValue(loc)
    }

    fun pushLocationHistory(touristId: String, lat: Double, lng: Double) {
        val entry = LocationEntry(lat, lng, System.currentTimeMillis())
        db.getReference("LocationHistory/$touristId").push().setValue(entry)
    }

    fun sendSos(touristId: String, lat: Double, lng: Double) {
        val sos = SosAlert(lat, lng, System.currentTimeMillis(), "ACTIVE")
        db.getReference("SOS/$touristId").setValue(sos)
        createAlert(touristId, "SOS", "HIGH", lat, lng)
        updateTouristStatus(touristId, "SOS")
    }

    fun clearSos(touristId: String) {
        db.getReference("SOS/$touristId").removeValue()
        updateTouristStatus(touristId, "SAFE")
    }

    fun createAlert(touristId: String, type: String, risk: String, lat: Double, lng: Double) {
        val alert = Alert(touristId, type, risk, lat, lng, System.currentTimeMillis())
        db.getReference("Alerts").push().setValue(alert)
    }

    fun updateTouristStatus(touristId: String, status: String) {
        db.getReference("Tourists/$touristId/status").setValue(status)
        db.getReference("LiveLocation/$touristId/status").setValue(status)
    }
}
