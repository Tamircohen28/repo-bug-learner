package fix.test.staff

import scala.concurrent.Future

object StaffQueryMissingAppDefIdInput {

  trait StaffMembersAdapter {
    def getAllStaffMembers(): Future[Seq[String]]
    def getAllStaffMembers(appDefId: String): Future[Seq[String]]
    def queryAllStaffMembers(): Future[Seq[String]]
    def listActiveStaffMembers(filter: String): Future[Seq[String]]
    def findAllStaffMembers(appDefId: String): Future[Seq[String]]
    def fetchOrCreateDefaultStaffMember(): Future[String]
    def deleteStaffMember(id: String): Future[Unit]
    def assignCustomScheduleToStaffMember(scheduleId: String, id: String): Future[Unit]
    def createNonDefaultStaffMember(payload: String): Future[String]
    def disconnectUser(id: String): Future[Unit]
    def handleStaffConnectedToUser(event: String): Future[Unit]
    def getStaffMemberByResourceId(id: String): Future[Option[String]]
  }

  trait MembersRepository {
    // CRM members API — should never match (no Staff in method name).
    def getMembers(contactIds: Seq[String]): Future[Seq[String]]
  }

  class Client(
    staffMembersAdapter: StaffMembersAdapter,
    membersRepository: MembersRepository,
  ) {

    val appDefId: String = "example-app"

    // BAD: zero-arg unbounded enumeration
    def all(): Future[Seq[String]] =
      staffMembersAdapter.getAllStaffMembers() 

    // BAD: query verb, no scoping arg
    def queryAll(): Future[Seq[String]] =
      staffMembersAdapter.queryAllStaffMembers() 

    // BAD: list verb with non-appDefId positional arg
    def listActive(): Future[Seq[String]] =
      staffMembersAdapter.listActiveStaffMembers("active") 

    // GOOD: positional appDefId argument
    def allScoped(): Future[Seq[String]] =
      staffMembersAdapter.getAllStaffMembers(appDefId)

    // GOOD: named appDefId argument
    def findAllScoped(): Future[Seq[String]] =
      staffMembersAdapter.findAllStaffMembers(appDefId = appDefId)

    // GOOD: singleton fetch (no plural) — not a query
    def defaultStaff(): Future[String] =
      staffMembersAdapter.fetchOrCreateDefaultStaffMember()

    // GOOD: lookup-by-ID singleton
    def byResource(id: String): Future[Option[String]] =
      staffMembersAdapter.getStaffMemberByResourceId(id)

    // GOOD: mutator verbs — no filter to scope
    def remove(id: String): Future[Unit] =
      staffMembersAdapter.deleteStaffMember(id)

    def assign(sId: String, id: String): Future[Unit] =
      staffMembersAdapter.assignCustomScheduleToStaffMember(sId, id)

    def create(p: String): Future[String] =
      staffMembersAdapter.createNonDefaultStaffMember(p)

    def disconnect(id: String): Future[Unit] =
      staffMembersAdapter.disconnectUser(id)

    def handle(e: String): Future[Unit] =
      staffMembersAdapter.handleStaffConnectedToUser(e)

    // GOOD: CRM members API — receiver matches but method is `getMembers`,
    // not a *StaffMembers method, so should NOT fire.
    def crmMembers(ids: Seq[String]): Future[Seq[String]] =
      membersRepository.getMembers(ids)
  }
}
