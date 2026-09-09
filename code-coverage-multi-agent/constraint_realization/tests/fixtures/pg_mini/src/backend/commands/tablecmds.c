static void
MarkFooPending(void)
{
	Form_pg_foo form = NULL;
	form->foopend = true;
}

static void
MarkBarFlag(void)
{
	Form_pg_foo form = NULL;
	form->barflag = true;
}

static void
ATExecDetachPartition(bool concurrent)
{
	Oid parentrelid = 0;
	LOCKTAG tag;

	if (!concurrent)
		RemoveInheritance();
	else
		MarkFooPending();

	PopActiveSnapshot();
	CommitTransactionCommand();
	SET_LOCKTAG_RELATION(tag, MyDatabaseId, parentrelid);
	WaitForLockersMultiple(list_make1(&tag), AccessExclusiveLock, false);
}

static void
ATExecEnableAlways(void)
{
	MarkBarFlag();
}

static void
ATExecCmd(void)
{
	switch (cmd->subtype)
	{
		case AT_AddColumn:
			break;
		case AT_DetachPartition:
			ATExecDetachPartition(cmd->concurrent);
			break;
		case AT_EnableAlways:
			ATExecEnableAlways();
			break;
	}
}
